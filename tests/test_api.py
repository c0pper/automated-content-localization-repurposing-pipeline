from __future__ import annotations

from tests.helpers import (
    auth_headers,
    complete_job,
    confirm,
    idem_headers,
    make_client,
    make_settings,
    reach_gate,
    selection_cell,
    set_voice_profile,
    source_file,
    submit_job,
    wait_for_status,
)


def test_creator_journey_submit_gate_select_localize_and_review(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["checks"]["queue"] == "ok"
        set_voice_profile(client)

        accepted = submit_job(client, source, target_languages=["es", "de"])
        job_id = accepted["job_id"]
        assert accepted["status"] == "RECEIVED"

        job = wait_for_status(client, job_id, {"AWAITING_SELECTION", "FAILED"})
        assert job["status"] == "AWAITING_SELECTION", job
        assert job["stage"] is None
        assert job["source_language"]["origin"] == "detected"
        assert len(job["segments"]) == 3
        assert job["review_url"]
        assert job["expires_at"]
        assert job["selection"] is None
        assert job["cost"]["projected_localization_usd"]

        # The review link works without the Workspace API key and shows Base Clips only.
        token = job["review_url"].rsplit("/", 1)[-1]
        review = client.get(f"/api/review/{token}")
        assert review.status_code == 200
        manifest = review.json()
        assert manifest["status"] == "AWAITING_SELECTION"
        assert all(segment["video_asset_url"] for segment in manifest["segments"])
        assert all(not segment["localized_assets"] for segment in manifest["segments"])

        gate = client.get(f"/api/jobs/{job_id}/selection", headers=auth_headers()).json()
        assert len(gate["cost_matrix"]) == 6

        cell = selection_cell(gate, 1, "es")
        changed = confirm(
            client,
            job_id,
            segment_ids=[1],
            languages=["es"],
            expected_total_usd="0.01",
            key="price-change",
        )
        assert changed.status_code == 409
        assert changed.json()["detail"]["code"] == "selection_price_changed"
        assert changed.json()["detail"]["details"]["current_total_usd"] == cell["total_usd"]

        accepted_selection = confirm(
            client,
            job_id,
            segment_ids=[1],
            languages=["es"],
            expected_total_usd=cell["total_usd"],
            key="confirm-1",
        )
        assert accepted_selection.status_code == 202
        assert accepted_selection.json()["status"] == "PROCESSING"
        assert accepted_selection.json()["stage"] == "localization"
        assert accepted_selection.json()["selection"]["segment_ids"] == [1]

        completed = wait_for_status(client, job_id, {"COMPLETED", "FAILED"})
        assert completed["status"] == "COMPLETED", completed
        assert completed["stage"] is None
        assert completed["expires_at"] is None

        by_id = {segment["segment_id"]: segment for segment in completed["segments"]}
        assert set(by_id[1]["localized_assets"]) == {"es"}
        assert by_id[1]["localized_copy"]["es"]["hook_title"].startswith("[es]")
        assert by_id[2]["localized_assets"] == {}
        assert by_id[3]["localized_assets"] == {}

        bundle = client.get(f"/api/jobs/{job_id}/bundle", headers=auth_headers()).json()
        assert bundle["status"] == "COMPLETED"
        assert set(bundle["segments"][0]["localized_assets"]) == {"es"}
        assert "source_text" not in bundle["segments"][0]
        assert "masters" not in str(bundle)

        # Stable asset URLs redirect to a short-lived presigned URL.
        asset = client.get(
            f"/api/review/{token}/assets/clip_1_es", follow_redirects=False
        )
        assert asset.status_code == 302
        assert "signature=" in asset.headers["location"]
        api_asset = client.get(
            f"/api/jobs/{job_id}/assets/base_1",
            headers=auth_headers(),
            follow_redirects=False,
        )
        assert api_asset.status_code == 302

        cost = client.get(f"/api/jobs/{job_id}/cost", headers=auth_headers()).json()
        assert float(cost["spent_usd"]) > 0
        assert any(entry["provider"] == "elevenlabs" for entry in cost["entries"])

        events = client.get(
            f"/api/jobs/{job_id}/events", headers=auth_headers()
        ).json()["items"]
        types = [event["type"] for event in events]
        assert "gate_opened" in types
        assert "selection_confirmed" in types
        assert "bundle_ready" in types


def test_empty_selection_completes_with_base_clips_only(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        job = reach_gate(client, source)
        assert job["status"] == "AWAITING_SELECTION"

        response = confirm(
            client,
            job["job_id"],
            segment_ids=[],
            languages=[],
            expected_total_usd="0.00",
        )
        assert response.status_code == 202
        assert response.json()["stage"] == "delivery"

        completed = wait_for_status(client, job["job_id"], {"COMPLETED", "FAILED"})
        assert completed["status"] == "COMPLETED"
        assert len(completed["segments"]) == 3
        assert all(not segment["localized_assets"] for segment in completed["segments"])
        bundle = client.get(
            f"/api/jobs/{job['job_id']}/bundle", headers=auth_headers()
        ).json()
        assert all(not segment["localized_assets"] for segment in bundle["segments"])


def test_selection_rejects_widening_and_unknown_clips(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        job = reach_gate(client, source, target_languages=["es"])
        widened = confirm(
            client,
            job["job_id"],
            segment_ids=[1],
            languages=["de"],
            expected_total_usd="0.00",
            key="widen",
        )
        assert widened.status_code == 422
        assert widened.json()["detail"]["code"] == "invalid_selection"

        unknown = confirm(
            client,
            job["job_id"],
            segment_ids=[99],
            languages=["es"],
            expected_total_usd="0.00",
            key="unknown",
        )
        assert unknown.status_code == 422
        assert unknown.json()["detail"]["code"] == "invalid_selection"


def test_selection_gate_expires_and_notifies(tmp_path):
    settings = make_settings(tmp_path, run_worker=True, selection_gate_days=0)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        job = reach_gate(client, source)
        assert job["status"] == "AWAITING_SELECTION"

        expired = client.get(
            f"/api/jobs/{job['job_id']}/selection", headers=auth_headers()
        )
        assert expired.status_code == 410
        assert expired.json()["detail"]["code"] == "selection_expired"

        stored = client.get(
            f"/api/jobs/{job['job_id']}", headers=auth_headers()
        ).json()
        assert stored["status"] == "EXPIRED"

        events = client.get(
            f"/api/jobs/{job['job_id']}/events", headers=auth_headers()
        ).json()["items"]
        assert any(event["type"] == "selection_expired" for event in events)


def test_cancel_at_gate_keeps_base_clips_and_blocks_repeat(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        job = reach_gate(client, source)
        cancelled = client.post(
            f"/api/jobs/{job['job_id']}/cancel", headers=idem_headers("cancel-1")
        )
        assert cancelled.status_code == 202
        assert cancelled.json()["status"] == "CANCELLED"
        assert cancelled.json()["stage"] is None

        again = client.post(
            f"/api/jobs/{job['job_id']}/cancel", headers=idem_headers("cancel-2")
        )
        assert again.status_code == 409
        assert again.json()["detail"]["code"] == "invalid_state"

        token = job["review_url"].rsplit("/", 1)[-1]
        review = client.get(f"/api/review/{token}")
        assert review.status_code == 200
        assert all(segment["video_asset_url"] for segment in review.json()["segments"])


def test_auth_is_required_for_workspace_endpoints(tmp_path):
    settings = make_settings(tmp_path)

    with make_client(settings) as client:
        missing = client.get("/api/jobs")
        assert missing.status_code == 401
        assert missing.json()["detail"]["code"] == "unauthorized"

        wrong = client.get("/api/jobs", headers=auth_headers("wrong-key"))
        assert wrong.status_code == 401

        assert client.get("/api/jobs", headers=auth_headers()).status_code == 200


def test_submission_is_idempotent_and_rejects_key_reuse(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        body = {
            "source": {"type": "url", "url": str(source)},
            "target_languages": ["es"],
        }
        first = client.post("/api/jobs", json=body, headers=idem_headers("same"))
        second = client.post("/api/jobs", json=body, headers=idem_headers("same"))
        assert first.status_code == 202
        assert second.status_code == 202
        assert second.json() == first.json()
        assert len(client.get("/api/jobs", headers=auth_headers()).json()["items"]) == 1

        different = client.post(
            "/api/jobs",
            json={**body, "target_languages": ["de"]},
            headers=idem_headers("same"),
        )
        assert different.status_code == 409
        assert different.json()["detail"]["code"] == "idempotency_key_reuse"

        missing = client.post("/api/jobs", json=body, headers=auth_headers())
        assert missing.status_code == 422
        assert missing.json()["detail"]["code"] == "idempotency_key_required"


def test_invalid_submissions_are_rejected_before_paid_work(tmp_path):
    settings = make_settings(tmp_path)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        too_many = client.post(
            "/api/jobs",
            json={
                "source": {"type": "url", "url": str(source)},
                "target_languages": ["es", "de", "fr", "it"],
            },
            headers=idem_headers("many"),
        )
        assert too_many.status_code == 422
        assert too_many.json()["detail"]["code"] == "too_many_languages"

        conflict = client.post(
            "/api/jobs",
            json={
                "source": {"type": "url", "url": str(source)},
                "source_language": "es",
                "target_languages": ["es"],
            },
            headers=idem_headers("conflict"),
        )
        assert conflict.status_code == 422
        assert conflict.json()["detail"]["code"] == "source_target_conflict"

        bad_model = client.post(
            "/api/jobs",
            json={
                "source": {"type": "url", "url": str(source)},
                "target_languages": ["es"],
                "model_overrides": {"translation": "not-a-model"},
            },
            headers=idem_headers("model"),
        )
        assert bad_model.status_code == 422
        assert bad_model.json()["detail"]["code"] == "invalid_model"

        no_targets = client.post(
            "/api/jobs",
            json={"source": {"type": "url", "url": str(source)}, "target_languages": []},
            headers=idem_headers("empty"),
        )
        assert no_targets.status_code == 422
        assert no_targets.json()["detail"]["code"] == "no_target_languages"


def test_unsupported_format_and_unknown_job(tmp_path):
    settings = make_settings(tmp_path)
    notes = tmp_path / "notes.txt"
    notes.write_text("nope")

    with make_client(settings) as client:
        response = client.post(
            "/api/jobs",
            json={"source": {"type": "url", "url": str(notes)}, "target_languages": ["es"]},
            headers=idem_headers("notes"),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "unsupported_media_format"

        missing = client.get("/api/jobs/job_missing", headers=auth_headers())
        assert missing.status_code == 404


def test_webhook_requires_secret_and_event_id(tmp_path):
    settings = make_settings(tmp_path, run_worker=True, webhook_secret="top-secret")
    source = source_file(tmp_path)
    body = {"source": {"type": "url", "url": str(source)}, "target_languages": ["es"]}

    with make_client(settings) as client:
        unauthorized = client.post(
            "/api/webhooks/drive", json=body, headers=idem_headers("event-1")
        )
        assert unauthorized.status_code == 401

        missing_key = client.post(
            "/api/webhooks/drive",
            json=body,
            headers={"X-Webhook-Secret": "top-secret"},
        )
        assert missing_key.status_code == 422

        authorized = client.post(
            "/api/webhooks/drive",
            json=body,
            headers={**idem_headers("event-2"), "X-Webhook-Secret": "top-secret"},
        )
        assert authorized.status_code == 202
        duplicate = client.post(
            "/api/webhooks/drive",
            json=body,
            headers={**idem_headers("event-2"), "X-Webhook-Secret": "top-secret"},
        )
        assert duplicate.json() == authorized.json()

        unknown = client.post(
            "/api/webhooks/vimeo",
            json=body,
            headers={**idem_headers("event-3"), "X-Webhook-Secret": "top-secret"},
        )
        assert unknown.status_code == 422


def test_review_link_rotation_and_revocation(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        job = reach_gate(client, source)
        old_token = job["review_url"].rsplit("/", 1)[-1]

        rotated = client.post(
            f"/api/jobs/{job['job_id']}/review-link",
            headers=idem_headers("rotate-1"),
        )
        assert rotated.status_code == 200
        new_url = rotated.json()["review_url"]
        assert new_url != job["review_url"]

        assert client.get(f"/api/review/{old_token}").status_code == 404
        assert client.get(new_url.replace("http://testserver", "")).status_code == 200

        revoked = client.delete(
            f"/api/jobs/{job['job_id']}/review-link",
            headers=idem_headers("revoke-1"),
        )
        assert revoked.status_code == 204
        new_token = new_url.rsplit("/", 1)[-1]
        assert client.get(f"/api/review/{new_token}").status_code == 404


def test_workspace_settings_and_voice_profile(tmp_path):
    settings = make_settings(tmp_path)

    with make_client(settings) as client:
        workspace = client.get("/api/workspace", headers=auth_headers()).json()
        assert workspace["workspace_id"] == "ws_default"
        assert workspace["job_budget_usd"] == "50.00"
        assert workspace["voice_profile"] is None

        updated = client.put(
            "/api/workspace",
            json={
                "target_language_allowlist": ["es", "fr"],
                "default_models": {},
                "job_budget_usd": "10.00",
                "monthly_budget_usd": "100.00",
                "max_concurrent_jobs": 1,
            },
            headers=auth_headers(),
        )
        assert updated.status_code == 200
        assert updated.json()["target_language_allowlist"] == ["es", "fr"]
        assert updated.json()["job_budget_usd"] == "10.00"

        too_concurrent = client.put(
            "/api/workspace",
            json={
                "target_language_allowlist": ["es"],
                "default_models": {},
                "job_budget_usd": "10.00",
                "monthly_budget_usd": "100.00",
                "max_concurrent_jobs": 99,
            },
            headers=auth_headers(),
        )
        assert too_concurrent.status_code == 422
        assert too_concurrent.json()["detail"]["code"] == "invalid_concurrency"

        set_voice_profile(client, "voice_abc")
        profile = client.get("/api/workspace/voice-profile", headers=auth_headers())
        assert profile.json()["voice_profile"]["voice_id"] == "voice_abc"

        deleted = client.delete(
            "/api/workspace/voice-profile", headers=idem_headers("voice-delete")
        )
        assert deleted.status_code == 204
        assert (
            client.get("/api/workspace/voice-profile", headers=auth_headers()).json()[
                "voice_profile"
            ]
            is None
        )


def test_workspace_purge_is_two_step_and_keeps_settings(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        set_voice_profile(client, "voice_keep")
        completed = complete_job(client, source)
        assert completed["status"] == "COMPLETED"

        dry_run = client.post(
            "/api/workspace/purge/dry-run", headers=idem_headers("purge-dry")
        )
        assert dry_run.status_code == 200
        preview = dry_run.json()
        assert preview["jobs"] == 1
        assert preview["base_clips"] == 3
        assert preview["confirmation_token"]

        confirmed = client.post(
            "/api/workspace/purge",
            json={
                "workspace_id": "ws_default",
                "confirmation_token": preview["confirmation_token"],
            },
            headers=idem_headers("purge-confirm"),
        )
        assert confirmed.status_code == 202
        purge_id = confirmed.json()["purge_id"]

        status = client.get(
            f"/api/workspace/purge/{purge_id}", headers=auth_headers()
        ).json()
        assert status["status"] == "completed"

        assert client.get("/api/jobs", headers=auth_headers()).json()["items"] == []
        assert (
            client.get(f"/api/jobs/{completed['job_id']}", headers=auth_headers()).status_code
            == 404
        )
        workspace = client.get("/api/workspace", headers=auth_headers()).json()
        assert workspace["voice_profile"]["voice_id"] == "voice_keep"
        assert not (settings.data_dir / "objects" / "jobs" / completed["job_id"]).exists()


def test_purge_requires_terminal_jobs(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        job = reach_gate(client, source)
        dry_run = client.post(
            "/api/workspace/purge/dry-run", headers=idem_headers("dry-active")
        ).json()
        confirmed = client.post(
            "/api/workspace/purge",
            json={
                "workspace_id": "ws_default",
                "confirmation_token": dry_run["confirmation_token"],
            },
            headers=idem_headers("confirm-active"),
        )
        assert confirmed.status_code == 409
        assert confirmed.json()["detail"]["code"] == "active_jobs"
        assert confirmed.json()["detail"]["details"]["job_ids"] == [job["job_id"]]


def test_derived_jobs_copy_and_localization(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        set_voice_profile(client)
        parent = complete_job(client, source)
        assert parent["status"] == "COMPLETED"

        copy_child = client.post(
            f"/api/jobs/{parent['job_id']}/derive",
            json={"mode": "copy"},
            headers=idem_headers("derive-copy"),
        )
        assert copy_child.status_code == 202
        copy_id = copy_child.json()["job_id"]
        assert copy_child.json()["parent_job_id"] == parent["job_id"]
        copy_done = wait_for_status(client, copy_id, {"COMPLETED", "FAILED"})
        assert copy_done["status"] == "COMPLETED", copy_done
        assert copy_done["copy_origin"] == {
            "clips": "generated",
            "linkedin": "parent",
            "newsletter": "parent",
        }
        assert copy_done["content"] == parent["content"]

        localization_child = client.post(
            f"/api/jobs/{parent['job_id']}/derive",
            json={"mode": "localization", "target_languages": ["fr"]},
            headers=idem_headers("derive-loc"),
        )
        assert localization_child.status_code == 202
        child = localization_child.json()
        assert child["status"] == "AWAITING_SELECTION"
        assert child["target_languages"] == ["fr"]
        assert child["source_language"]["code"] == parent["source_language"]["code"]

        gate = client.get(
            f"/api/jobs/{child['job_id']}/selection", headers=auth_headers()
        ).json()
        cell = selection_cell(gate, 1, "fr")
        response = confirm(
            client,
            child["job_id"],
            segment_ids=[1],
            languages=["fr"],
            expected_total_usd=cell["total_usd"],
            key="derive-loc-select",
        )
        assert response.status_code == 202
        done = wait_for_status(client, child["job_id"], {"COMPLETED", "FAILED"})
        assert done["status"] == "COMPLETED", done
        assert set(done["segments"][0]["localized_assets"]) == {"fr"}

        # The original bundle is untouched.
        original = client.get(
            f"/api/jobs/{parent['job_id']}/bundle", headers=auth_headers()
        ).json()
        assert set(original["segments"][0]["localized_assets"]) == {"es"}


def test_derive_rejects_ineligible_parent(tmp_path):
    settings = make_settings(tmp_path, run_worker=True)
    source = source_file(tmp_path)

    with make_client(settings) as client:
        job = reach_gate(client, source)
        response = client.post(
            f"/api/jobs/{job['job_id']}/derive",
            json={"mode": "copy"},
            headers=idem_headers("derive-gate"),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "parent_not_eligible"
