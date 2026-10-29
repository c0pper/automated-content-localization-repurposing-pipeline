"""Object-store contract suite, run against both the local store and Silo.

Clients reach both backends over plain HTTP with the presigned URLs the store hands out, as a
browser would. Silo is emulated by a moto S3 server. Moto does not check presigned
signatures, so the Silo client goes through a SigV4 query-signature check first, the same
check Silo applies. That check is what proves each URL is bound to one method, key and part.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import boto3
import httpx
import pytest
from botocore.client import Config as BotoConfig
from fastapi.testclient import TestClient

from app.adapters.silo_object_store import SiloObjectStore
from app.config import Settings
from app.container import build_container
from app.domain.errors import ExternalServiceError
from app.main import create_app
from app.ports.infra import ObjectStore, UploadedPart
from tests.helpers import make_settings

_PART_BYTES = 5 * 1024 * 1024  # The S3 minimum for every part but the last.
_TTL = 300
_BUCKET = "pipeline"


@dataclass
class Backend:
    store: ObjectStore
    http: httpx.Client
    part_param: str


class SigV4QueryGate(httpx.BaseTransport):
    """Reject requests whose presigned SigV4 query signature does not verify, as S3 does."""

    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key
        self._inner = httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if not self._verifies(request):
            return httpx.Response(403, request=request)
        return self._inner.handle_request(request)

    def _verifies(self, request: httpx.Request) -> bool:
        params = parse_qsl(request.url.query.decode(), keep_blank_values=True)
        query = dict(params)
        signature = query.get("X-Amz-Signature", "")
        if query.get("X-Amz-Algorithm") != "AWS4-HMAC-SHA256" or not signature:
            return False
        signed_at = datetime.strptime(query["X-Amz-Date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if datetime.now(UTC) > signed_at + timedelta(seconds=int(query["X-Amz-Expires"])):
            return False

        _, date, region, service, _ = query["X-Amz-Credential"].split("/")
        signed_headers = query["X-Amz-SignedHeaders"]
        canonical_query = "&".join(
            f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}"
            for name, value in sorted(params)
            if name != "X-Amz-Signature"
        )
        canonical_headers = "".join(
            f"{name}:{request.headers[name].strip()}\n" for name in signed_headers.split(";")
        )
        canonical_request = "\n".join(
            [
                request.method,
                request.url.raw_path.split(b"?")[0].decode(),
                canonical_query,
                canonical_headers,
                signed_headers,
                "UNSIGNED-PAYLOAD",
            ]
        )
        scope = f"{date}/{region}/{service}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                query["X-Amz-Date"],
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signing_key = f"AWS4{self._secret_key}".encode()
        for part in (date, region, service, "aws4_request"):
            signing_key = hmac.new(signing_key, part.encode(), hashlib.sha256).digest()
        expected = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


@pytest.fixture(scope="module")
def silo_endpoint() -> Iterator[str]:
    from moto.server import ThreadedMotoServer

    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    _, port = server.get_host_and_port()
    endpoint = f"http://127.0.0.1:{port}"
    boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="access",
        aws_secret_access_key="secret",
    ).create_bucket(Bucket=_BUCKET)
    yield endpoint
    server.stop()


@pytest.fixture(params=["local", "silo"])
def backend(request, tmp_path) -> Iterator[Backend]:
    if request.param == "local":
        container = build_container(make_settings(tmp_path))
        with TestClient(create_app(container=container)) as client:
            yield Backend(store=container.store, http=client, part_param="part_number")
        return

    endpoint = request.getfixturevalue("silo_endpoint")
    settings = Settings(
        _env_file=None,
        environment="test",
        data_dir=tmp_path / "data",
        object_store_backend="silo",
        silo_endpoint=endpoint,
        silo_bucket=_BUCKET,
        silo_access_key="access",
        silo_secret_key="secret",
    )
    with httpx.Client(transport=SigV4QueryGate("secret")) as client:
        yield Backend(store=SiloObjectStore(settings), http=client, part_param="partNumber")


def _upload_key() -> str:
    # The moto server outlives a single test, so every test writes its own key.
    return f"uploads/{uuid.uuid4().hex}/source.mp4"


def _with_param(url: str, name: str, value: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value if key == name else current)
        for key, current in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


async def _put_part(backend: Backend, key: str, upload_id: str, number: int, data: bytes):
    url = await backend.store.presign_part(key, upload_id, number, ttl_seconds=_TTL)
    response = backend.http.put(url, content=data)
    assert response.status_code == 200, response.text
    return UploadedPart(part_number=number, etag=response.headers["ETag"])


async def test_multipart_upload_assembles_one_object_of_the_summed_size(backend):
    key = _upload_key()
    first, last = b"a" * _PART_BYTES, b"b" * 1024

    upload_id = await backend.store.initiate_multipart(key, content_type="video/mp4")
    # Parts may arrive out of order; completion lists them in part-number order.
    second = await _put_part(backend, key, upload_id, 2, last)
    first_part = await _put_part(backend, key, upload_id, 1, first)
    await backend.store.complete_multipart(key, upload_id, [first_part, second])

    head = await backend.store.head(key)
    assert head is not None
    assert head.size == len(first) + len(last)
    assert head.content_type == "video/mp4"
    download = backend.http.get(await backend.store.presign(key, ttl_seconds=_TTL))
    assert download.status_code == 200
    assert hashlib.sha256(download.content).digest() == hashlib.sha256(first + last).digest()


async def test_retrying_a_part_replaces_it(backend):
    key = _upload_key()
    upload_id = await backend.store.initiate_multipart(key, content_type="video/mp4")
    await _put_part(backend, key, upload_id, 1, b"stale")
    part = await _put_part(backend, key, upload_id, 1, b"fresh")

    await backend.store.complete_multipart(key, upload_id, [part])

    assert (await backend.store.head(key)).size == len(b"fresh")


async def test_abort_leaves_no_object(backend):
    key = _upload_key()
    upload_id = await backend.store.initiate_multipart(key, content_type="video/mp4")
    part = await _put_part(backend, key, upload_id, 1, b"x" * 1024)

    await backend.store.abort_multipart(key, upload_id)
    await backend.store.abort_multipart(key, upload_id)  # Idempotent.

    assert await backend.store.head(key) is None
    # Not asserting `retryable`: moto answers 500 here where S3 answers NoSuchUpload.
    with pytest.raises(ExternalServiceError):
        await backend.store.complete_multipart(key, upload_id, [part])
    assert await backend.store.head(key) is None


async def test_complete_rejects_a_wrong_etag(backend):
    key = _upload_key()
    upload_id = await backend.store.initiate_multipart(key, content_type="video/mp4")
    await _put_part(backend, key, upload_id, 1, b"x" * 1024)

    with pytest.raises(ExternalServiceError) as raised:
        await backend.store.complete_multipart(
            key, upload_id, [UploadedPart(part_number=1, etag='"0123456789abcdef"')]
        )

    assert not raised.value.retryable
    assert await backend.store.head(key) is None


async def test_complete_rejects_an_undersized_middle_part(backend):
    key = _upload_key()
    upload_id = await backend.store.initiate_multipart(key, content_type="video/mp4")
    small = await _put_part(backend, key, upload_id, 1, b"x" * 1024)
    last = await _put_part(backend, key, upload_id, 2, b"y" * 1024)

    with pytest.raises(ExternalServiceError):
        await backend.store.complete_multipart(key, upload_id, [small, last])

    assert await backend.store.head(key) is None


async def test_head_of_a_missing_object_is_none(backend):
    assert await backend.store.head(_upload_key()) is None


async def test_presigned_get_cannot_be_used_to_put(backend, tmp_path):
    key = _upload_key()
    source = tmp_path / "original.mp4"
    source.write_bytes(b"original")
    await backend.store.put(source, key)
    url = await backend.store.presign(key, ttl_seconds=_TTL)

    response = backend.http.put(url, content=b"overwritten")

    assert response.status_code == 403
    assert backend.http.get(url).content == b"original"


async def test_presigned_get_serves_a_clip_as_video_mp4(backend, tmp_path):
    """Firefox refuses a <video> source served as binary/octet-stream."""
    key = _upload_key()
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"clip")
    await backend.store.put(source, key)

    response = backend.http.get(await backend.store.presign(key, ttl_seconds=_TTL))

    assert response.headers["content-type"] == "video/mp4"


async def test_part_url_is_bound_to_its_method_part_and_key(backend):
    key = _upload_key()
    upload_id = await backend.store.initiate_multipart(key, content_type="video/mp4")
    url = await backend.store.presign_part(key, upload_id, 1, ttl_seconds=_TTL)

    other_part = _with_param(url, backend.part_param, "2")
    other_key = url.replace(key, _upload_key())

    assert backend.http.put(other_part, content=b"x").status_code == 403
    assert backend.http.put(other_key, content=b"x").status_code == 403
    assert backend.http.get(url).status_code == 403
    assert backend.http.put(url, content=b"x").status_code == 200


def test_sigv4_gate_rejects_a_tampered_signature():
    client = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:9",
        region_name="us-east-1",
        aws_access_key_id="access",
        aws_secret_access_key="secret",
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    url = client.generate_presigned_url(
        "get_object", Params={"Bucket": _BUCKET, "Key": "k"}, ExpiresIn=60
    )
    tampered = _with_param(url, "X-Amz-Signature", "0" * 64)

    assert SigV4QueryGate("secret")._verifies(httpx.Request("GET", url))
    assert not SigV4QueryGate("secret")._verifies(httpx.Request("GET", tampered))
    assert not SigV4QueryGate("other")._verifies(httpx.Request("GET", url))


async def test_local_presigned_urls_expire(tmp_path, monkeypatch):
    container = build_container(make_settings(tmp_path))
    store = container.store
    url = await store.presign("jobs/job_1/clip.mp4", ttl_seconds=60)
    query = dict(parse_qsl(urlsplit(url).query))

    monkeypatch.setattr(time, "time", lambda: int(query["expires"]) + 1)

    assert not store.verify_presigned(
        "GET",
        "jobs/job_1/clip.mp4",
        expires=int(query["expires"]),
        signature=query["signature"],
    )
