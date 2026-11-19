#!/usr/bin/env bash
# Creates the Ember Optics datastore: uploads ember_docs/ to a bucket, creates an
# Agent Search datastore, imports the documents, and waits for the import.
# Usage: ./challenge-2-rag-and-search/create_datastore.sh [PROJECT_ID]
#        (or set PROJECT_ID in the environment)
set -euo pipefail

PROJECT_ID="${1:-${PROJECT_ID:-}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: $0 PROJECT_ID   (or set PROJECT_ID)" >&2
  exit 1
fi
DATASTORE_ID="${DATASTORE_ID:-ember-docs}"
BUCKET="gs://${PROJECT_ID}-ember-docs"
BASE="https://discoveryengine.googleapis.com/v1"
API="${BASE}/projects/${PROJECT_ID}/locations/global/collections/default_collection/dataStores"
DOCS_DIR="$(dirname "$0")/ember_docs"

call() {  # call METHOD URL [BODY]
  curl -sS -X "$1" "$2" ${3:+-d "$3"} \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "X-Goog-User-Project: ${PROJECT_ID}" \
    -H "Content-Type: application/json"
}

json() {  # json FIELD: read a top-level field from JSON on stdin
  python3 -c "import json,sys; print(json.load(sys.stdin).get('$1', ''))"
}

gcloud services enable discoveryengine.googleapis.com storage.googleapis.com --project "$PROJECT_ID"
gcloud storage buckets describe "$BUCKET" >/dev/null 2>&1 ||
  gcloud storage buckets create "$BUCKET" --project "$PROJECT_ID" --location US --uniform-bucket-level-access
gcloud storage cp "$DOCS_DIR"/*.txt "$BUCKET/ember_docs/"

echo "Creating datastore ${DATASTORE_ID}..."
CREATED="$(call POST "${API}?dataStoreId=${DATASTORE_ID}" '{
  "displayName": "Ember Optics docs",
  "industryVertical": "GENERIC",
  "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
  "contentConfig": "CONTENT_REQUIRED"
}')"
STATUS="$(echo "$CREATED" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error', {}).get('status', ''))")"
if [[ -n "$STATUS" && "$STATUS" != "ALREADY_EXISTS" ]]; then
  echo "Could not create datastore: $CREATED" >&2
  exit 1
fi
until [[ "$(call GET "${API}/${DATASTORE_ID}" | json name)" ]]; do sleep 5; done

echo "Importing documents..."
OPERATION="$(call POST "${API}/${DATASTORE_ID}/branches/0/documents:import" "{
  \"gcsSource\": {\"inputUris\": [\"${BUCKET}/ember_docs/*.txt\"], \"dataSchema\": \"content\"},
  \"reconciliationMode\": \"INCREMENTAL\"
}" | json name)"

until [[ "$(call GET "${BASE}/${OPERATION}" | json done)" == "True" ]]; do
  echo "  import running..."
  sleep 15
done
call GET "${BASE}/${OPERATION}" | python3 -c "
import json, sys
op = json.load(sys.stdin)
if 'error' in op:
    sys.exit(f\"Import failed: {op['error']}\")
print('Import complete:', op.get('metadata', {}).get('successCount', '?'), 'documents')"
echo "Datastore ready. Set DATASTORE_ID=${DATASTORE_ID} in .env."
