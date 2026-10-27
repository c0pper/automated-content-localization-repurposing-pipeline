#!/usr/bin/env bash
# Deployment smoke test: submit a synthetic Job, confirm the Selection Gate, wait for
# COMPLETED and resolve the review link. Requires curl and python3 on the host.
#
#   API_BASE_URL=https://pipeline.example.com \
#   PIPELINE_WORKSPACE_API_KEY=... \
#   INPUT_URL=https://example.com/sample.mp4 \
#   ./deploy/smoke.sh
set -euo pipefail

API_BASE_URL="${API_BASE_URL:?set API_BASE_URL}"
PIPELINE_WORKSPACE_API_KEY="${PIPELINE_WORKSPACE_API_KEY:?set PIPELINE_WORKSPACE_API_KEY}"
INPUT_URL="${INPUT_URL:?set INPUT_URL to a small reachable mp4}"
TARGET_LANGUAGE="${TARGET_LANGUAGE:-es}"

api() {
    curl -fsS -H "Authorization: Bearer $PIPELINE_WORKSPACE_API_KEY" "$@"
}

json() {
    python3 -c "import json,sys; print(json.load(sys.stdin)$1)"
}

echo "Submitting $INPUT_URL"
job_id=$(api -X POST "$API_BASE_URL/api/jobs" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: smoke-$(date +%s)" \
    -d "{\"input_url\":\"$INPUT_URL\",\"target_languages\":[\"$TARGET_LANGUAGE\"]}" \
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
