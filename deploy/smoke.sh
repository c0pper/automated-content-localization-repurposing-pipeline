#!/usr/bin/env bash
# Deployment smoke test: upload a Source Recording through /api/uploads and Caddy to Silo,
# check Silo upload CORS, submit it as a Job, confirm the Selection Gate, wait for
# COMPLETED and resolve the review link. Requires bash, curl, coreutils (dd, wc, seq,
# tr), awk and python3 on the host.
#
#   API_BASE_URL=https://pipeline.example.com \
#   PIPELINE_WORKSPACE_API_KEY=... \
#   SOURCE_FILE=./sample.mp4 \
#   FRONTEND_ORIGIN=https://app.example.com \
#   ./deploy/smoke.sh
set -euo pipefail

API_BASE_URL="${API_BASE_URL:?set API_BASE_URL}"
API_BASE_URL="${API_BASE_URL%/}"
PIPELINE_WORKSPACE_API_KEY="${PIPELINE_WORKSPACE_API_KEY:?set PIPELINE_WORKSPACE_API_KEY}"
SOURCE_FILE="${SOURCE_FILE:?set SOURCE_FILE to a small local mp4 with an audio track}"
SOURCE_CONTENT_TYPE="${SOURCE_CONTENT_TYPE:-video/mp4}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-$API_BASE_URL}"
FOREIGN_ORIGIN="${FOREIGN_ORIGIN:-https://smoke-foreign-origin.invalid}"
TARGET_LANGUAGE="${TARGET_LANGUAGE:-es}"

api() {
    curl -fsS -H "Authorization: Bearer $PIPELINE_WORKSPACE_API_KEY" "$@"
}

json() {
    python3 -c "import json,sys; print(json.load(sys.stdin)$1)"
}

# Prints the value of response header $1 (case-insensitive) from headers on stdin.
header() {
    tr -d '\r' | awk -v name="$1" 'tolower($0) ~ "^" tolower(name) ":" { sub(/^[^:]*:[ \t]*/, ""); print; exit }'
}

# Prints a presigned PUT URL for part $2 of upload $1.
part_url() {
    api "$API_BASE_URL/api/uploads/$1/parts?numbers=$2" | json "['parts'][0]['url']"
}

# Prints the Access-Control-Allow-Origin Silo grants origin $2 for a PUT to URL $1.
preflight() {
    curl -fsS -o /dev/null -D - -X OPTIONS "$1" \
        -H "Origin: $2" -H "Access-Control-Request-Method: PUT" | header Access-Control-Allow-Origin
}

size_bytes=$(wc -c <"$SOURCE_FILE" | tr -d ' ')
echo "Uploading $SOURCE_FILE ($size_bytes bytes)"
upload_request=$(python3 -c 'import json,sys; print(json.dumps({"filename": sys.argv[1], "content_type": sys.argv[2], "size_bytes": int(sys.argv[3])}))' \
    "$(basename "$SOURCE_FILE")" "$SOURCE_CONTENT_TYPE" "$size_bytes")
read -r upload_id key part_size part_count < <(api -X POST "$API_BASE_URL/api/uploads" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: smoke-upload-$(date +%s)" \
    -d "$upload_request" \
    | python3 -c "import json,sys; u=json.load(sys.stdin); print(u['upload_id'], u['key'], u['part_size_bytes'], u['part_count'])" \
    | tr -d '\r')
echo "upload_id=$upload_id key=$key parts=$part_count"

# Silo CORS (ADR 0022): the frontend origin may PUT, any other origin is refused.
cors_url=$(part_url "$upload_id" 1)
allowed=$(preflight "$cors_url" "$FRONTEND_ORIGIN")
[ "$allowed" = "$FRONTEND_ORIGIN" ] || { echo "Silo CORS refused $FRONTEND_ORIGIN (got '$allowed')"; exit 1; }
refused=$(preflight "$cors_url" "$FOREIGN_ORIGIN")
[ -z "$refused" ] || { echo "Silo CORS allowed $FOREIGN_ORIGIN (got '$refused')"; exit 1; }
echo "Silo CORS allows $FRONTEND_ORIGIN and refuses $FOREIGN_ORIGIN"

etags=""
for number in $(seq 1 "$part_count"); do
    headers=$(dd if="$SOURCE_FILE" bs="$part_size" skip=$((number - 1)) count=1 2>/dev/null \
        | curl -fsS -o /dev/null -D - -X PUT "$(part_url "$upload_id" "$number")" \
            -H "Origin: $FRONTEND_ORIGIN" -H "Content-Type:" --data-binary @-)
    etag=$(printf '%s' "$headers" | header ETag)
    [ -n "$etag" ] || { echo "Part $number returned no ETag"; exit 1; }
    etags="$etags$etag"$'\n'
    echo "part $number etag=$etag"
done
exposed=$(printf '%s' "$headers" | header Access-Control-Expose-Headers)
case ",$(printf '%s' "$exposed" | tr -d ' ' | tr '[:upper:]' '[:lower:]')," in
    *,etag,*) ;;
    *) echo "Silo CORS does not expose ETag (got '$exposed')"; exit 1 ;;
esac

upload_status=$(printf '%s' "$etags" \
    | python3 -c 'import json,sys; print(json.dumps({"parts": [{"part_number": n, "etag": e} for n, e in enumerate(sys.stdin.read().split(), 1)]}))' \
    | api -X POST "$API_BASE_URL/api/uploads/$upload_id/complete" \
        -H "Content-Type: application/json" \
        -H "Idempotency-Key: smoke-complete-$upload_id" \
        --data-binary @- \
    | json "['status']")
[ "$upload_status" = "COMPLETED" ] || { echo "Upload did not complete (status=$upload_status)"; exit 1; }
echo "upload status=$upload_status"

echo "Submitting $key"
job_id=$(api -X POST "$API_BASE_URL/api/jobs" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: smoke-$(date +%s)" \
    -d "{\"source\":{\"type\":\"object\",\"key\":\"$key\"},\"target_languages\":[\"$TARGET_LANGUAGE\"]}" \
    | json "['job_id']")
echo "job_id=$job_id"

for _ in $(seq 1 120); do
    status=$(api "$API_BASE_URL/api/jobs/$job_id" | json "['status']")
    echo "status=$status"
    [ "$status" = "AWAITING_SELECTION" ] && break
    [ "$status" = "FAILED" ] && { api "$API_BASE_URL/api/jobs/$job_id"; exit 1; }
    sleep 5
done
[ "$status" = "AWAITING_SELECTION" ] || { echo "Job never reached the gate"; exit 1; }

gate=$(api "$API_BASE_URL/api/jobs/$job_id/selection")
segment_id=$(printf '%s' "$gate" | json "['segments'][0]['segment_id']")
total=$(printf '%s' "$gate" | python3 -c "import json,sys; gate=json.load(sys.stdin); print(next(cell['total_usd'] for cell in gate['cost_matrix'] if cell['segment_id']==int('$segment_id') and cell['language']=='$TARGET_LANGUAGE'))")
echo "Confirming segment $segment_id in $TARGET_LANGUAGE for $total"

api -X POST "$API_BASE_URL/api/jobs/$job_id/selection" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: smoke-confirm-$(date +%s)" \
    -d "{\"segment_ids\":[$segment_id],\"languages\":[\"$TARGET_LANGUAGE\"],\"expected_total_usd\":\"$total\"}" \
    >/dev/null

for _ in $(seq 1 180); do
    status=$(api "$API_BASE_URL/api/jobs/$job_id" | json "['status']")
    echo "status=$status"
    [ "$status" = "COMPLETED" ] && break
    [ "$status" = "FAILED" ] && { api "$API_BASE_URL/api/jobs/$job_id"; exit 1; }
    sleep 5
done
[ "$status" = "COMPLETED" ] || { echo "Job did not complete"; exit 1; }

review_url=$(api "$API_BASE_URL/api/jobs/$job_id" | json "['review_url']")
echo "Resolving $review_url"
api "$review_url" | python3 -c "import json,sys; manifest=json.load(sys.stdin); print('segments:', len(manifest['segments']))"

echo "Smoke test passed."
