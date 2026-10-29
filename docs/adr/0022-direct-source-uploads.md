---
status: accepted
---

# Creators upload Source Recordings directly to object storage

v1 originally accepted only a remote URL or a pre-uploaded Silo object key as Source Input. A Creator without their own hosting had no way to submit a file, and asking a Creator to type a raw `uploads/...` key is meaningless to them. This ADR supersedes that scope. A Creator can now upload a file as a Source Upload. The browser sends the file straight to the object store as a presigned S3 multipart upload. The API only checks the request, signs the parts and completes the upload. It never streams the bytes. Uploading always finishes before submission: the client then submits an ordinary Job with `source: {type: "object", key}`. No Job exists while an upload is in progress, and the Job state machine does not change.

The server generates every upload key. A presigned URL allows exactly one HTTP method on one key (and one part). On Silo, SigV4 provides this. The local store signs the method and part number in its HMAC, so a review download link can never be reused to write.

## Considered Options

- **Stream through FastAPI.** Rejected. Requests of up to 2 GB would tie up API workers and need Caddy body-size and timeout tuning. The API would stop being a thin control plane.
- **Single presigned PUT.** Rejected. One network drop restarts a multi-gigabyte transfer. Multipart retries only the failed part and reports real progress.
- **Job created first, in an `AWAITING_UPLOAD` state.** Rejected. It would add a state, a timeout and its own cleanup path to the lifecycle (ADR 0003, ADR 0006) only to represent bytes in transit.

## Consequences

- The `url` source and the API-level `object` source stay. The Creator UI offers Upload and URL only. Webhooks keep submitting URLs.
- Uploads are validated three times. When the upload starts, the declared extension, content type and size are checked against `max_source_bytes`. When it completes, the size of the assembled object is checked, and the object is deleted on a mismatch. Ingest still runs the authoritative media probe.
- Silo CORS must allow `PUT` from the frontend origin and expose `ETag`.
- Uploads that never complete are aborted after 24 hours. *(Amended in #45: this originally said "by a bucket lifecycle rule". Silo rejects the S3 `AbortIncompleteMultipartUpload` lifecycle rule, so the deployment sets Silo's stale-upload expiry to 24 hours instead.)* Completed Source Uploads never attached to a Job are deleted by the retention sweep after the Retention Window. Attached ones expire with the Source Recording (ADR 0009). A Workspace Purge already deletes `uploads/`.
- An upload interrupted by a page reload is lost in v1. Resuming across sessions is deferred.
- Uploads make no paid provider calls and do not touch the Cost Ledger.
