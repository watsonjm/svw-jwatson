#!/usr/bin/env bash
# Creates the two ADS datastores: uploads ads_data/ to a bucket, then creates an Agent
# Search datastore for policies and one for backend status, and imports both at once.
# Usage: ./challenge-6-dept-of-snow/create_datastores.sh [PROJECT_ID]
#        (or set PROJECT_ID in the environment)
set -euo pipefail

PROJECT_ID="${1:-${PROJECT_ID:-}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: $0 PROJECT_ID   (or set PROJECT_ID)" >&2
  exit 1
fi
POLICY_DATASTORE_ID="${POLICY_DATASTORE_ID:-ads-policies}"
BACKEND_DATASTORE_ID="${BACKEND_DATASTORE_ID:-ads-backend}"
BUCKET="gs://${PROJECT_ID}-ads"
BASE="https://discoveryengine.googleapis.com/v1"
API="${BASE}/projects/${PROJECT_ID}/locations/global/collections/default_collection/dataStores"
DATA_DIR="$(dirname "$0")/ads_data"

call() {  # call METHOD URL [BODY]
  curl -sS -X "$1" "$2" ${3:+-d "$3"} \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "X-Goog-User-Project: ${PROJECT_ID}" \
    -H "Content-Type: application/json"
}

json() {  # json FIELD: read a top-level field from JSON on stdin
  python3 -c "import json,sys; print(json.load(sys.stdin).get('$1', ''))"
}

create_datastore() {  # create_datastore ID DISPLAY_NAME: create it (fine if it exists) and wait until ready
  local id="$1" display_name="$2" created status
  echo "Creating datastore ${id}..."
  created="$(call POST "${API}?dataStoreId=${id}" "{
    \"displayName\": \"${display_name}\",
    \"industryVertical\": \"GENERIC\",
    \"solutionTypes\": [\"SOLUTION_TYPE_SEARCH\"],
    \"contentConfig\": \"CONTENT_REQUIRED\"
  }")"
  status="$(echo "$created" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error', {}).get('status', ''))")"
  if [[ -n "$status" && "$status" != "ALREADY_EXISTS" ]]; then
    echo "Could not create datastore ${id}: $created" >&2
    exit 1
  fi
  until [[ "$(call GET "${API}/${id}" | json name)" ]]; do sleep 5; done
}

start_import() {  # start_import ID FOLDER: start importing FOLDER/*.txt; prints the operation name
  call POST "${API}/$1/branches/0/documents:import" "{
    \"gcsSource\": {\"inputUris\": [\"${BUCKET}/$2/*.txt\"], \"dataSchema\": \"content\"},
    \"reconciliationMode\": \"INCREMENTAL\"
  }" | json name
}

wait_for_import() {  # wait_for_import ID OPERATION
  [[ -n "$2" ]] || { echo "Could not start the $1 import" >&2; exit 1; }
  until [[ "$(call GET "${BASE}/$2" | json done)" == "True" ]]; do
    echo "  $1 import running..."
    sleep 15
  done
  call GET "${BASE}/$2" | python3 -c "
import json, sys
op = json.load(sys.stdin)
if 'error' in op:
    sys.exit(f\"$1 import failed: {op['error']}\")
print('$1 import complete:', op.get('metadata', {}).get('successCount', '?'), 'documents')"
}

gcloud services enable discoveryengine.googleapis.com storage.googleapis.com --project "$PROJECT_ID"
gcloud storage buckets describe "$BUCKET" >/dev/null 2>&1 ||
  gcloud storage buckets create "$BUCKET" --project "$PROJECT_ID" --location US --uniform-bucket-level-access
gcloud storage cp "$DATA_DIR"/policies/*.txt "$BUCKET/policies/"
gcloud storage cp "$DATA_DIR"/backend/*.txt "$BUCKET/backend/"

create_datastore "$POLICY_DATASTORE_ID" "ADS policies"
create_datastore "$BACKEND_DATASTORE_ID" "ADS backend status"

# Both imports run at the same time on Google's side; then wait for each.
echo "Importing documents into both datastores..."
POLICY_IMPORT="$(start_import "$POLICY_DATASTORE_ID" policies)"
BACKEND_IMPORT="$(start_import "$BACKEND_DATASTORE_ID" backend)"
wait_for_import "$POLICY_DATASTORE_ID" "$POLICY_IMPORT"
wait_for_import "$BACKEND_DATASTORE_ID" "$BACKEND_IMPORT"

echo "Datastores ready. Set these in .env:"
echo "POLICY_DATASTORE_ID=${POLICY_DATASTORE_ID}"
echo "BACKEND_DATASTORE_ID=${BACKEND_DATASTORE_ID}"
