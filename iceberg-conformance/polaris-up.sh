#!/usr/bin/env bash
# Brings up the local Apache Polaris control catalog and seeds it.
#
# Four things here are not obvious and each one cost a failed attempt:
#
#  1. FILE storage is refused by default. Enabling it requires BOTH
#     ALLOW_INSECURE_STORAGE_TYPES and SUPPORTED_CATALOG_STORAGE_TYPES.
#  2. Enabling it then escalates the production-readiness check from warning to
#     fatal, so polaris.readiness.ignore-severe-issues is also required.
#  3. The container writes table metadata and the client writes data files, so
#     both need the same warehouse path -- hence the bind mount at an identical
#     absolute path, and --user so the files are owned by you.
#  5. DROP_WITH_PURGE_ENABLED is turned on deliberately. It is off by default,
#     and with it off Polaris refuses both drop_table?purgeRequested=true and
#     dropView -- which would put artificial red cells in the control column.
#     The control exists to be a permissive reference; a red cell in it should
#     mean the spec is unimplemented, not that a server flag is unset.
#  4. With --user, Hadoop's UserGroupInformation cannot resolve the uid and the
#     login fails with a 503 that reads like a storage error. Mounting
#     /etc/passwd read-only fixes it.
set -euo pipefail

WH="$(cd "$(dirname "$0")" && pwd)/.warehouse"
BASE=http://localhost:8181
CATALOG=quickstart_catalog

docker rm -f polaris >/dev/null 2>&1 || true
# Anything left from a run as the image's own uid is not ours to delete.
docker run --rm --user 0:0 -v "$WH:/wh" alpine:latest \
  sh -c 'rm -rf /wh/* /wh/.[!.]* 2>/dev/null || true' >/dev/null 2>&1 || true
mkdir -p "$WH" && chmod 777 "$WH"

docker run -d --name polaris -p 8181:8181 -p 8182:8182 \
  --user "$(id -u):$(id -g)" \
  -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro \
  -v "$WH:$WH" \
  -e HADOOP_USER_NAME="$(id -un)" \
  -e POLARIS_BOOTSTRAP_CREDENTIALS=POLARIS,root,s3cr3t \
  -e JAVA_OPTS_APPEND="-Dpolaris.features.\"ALLOW_INSECURE_STORAGE_TYPES\"=true -Dpolaris.features.\"SUPPORTED_CATALOG_STORAGE_TYPES\"=[\"FILE\"] -Dpolaris.readiness.ignore-severe-issues=true -Dpolaris.features.\"DROP_WITH_PURGE_ENABLED\"=true" \
  apache/polaris:latest >/dev/null

printf 'waiting for polaris'
for i in $(seq 1 60); do
  if curl -sf http://localhost:8182/q/health/ready >/dev/null 2>&1; then echo " ready (${i}s)"; break; fi
  printf '.'; sleep 1
done

TOK=$(curl -s -X POST $BASE/api/catalog/v1/oauth/tokens \
  -d grant_type=client_credentials -d client_id=root -d client_secret=s3cr3t \
  -d scope=PRINCIPAL_ROLE:ALL | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -o /dev/null -w "create catalog : HTTP %{http_code}\n" -X POST $BASE/api/management/v1/catalogs \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d "{\"catalog\":{\"name\":\"$CATALOG\",\"type\":\"INTERNAL\",
       \"properties\":{\"default-base-location\":\"file://$WH\"},
       \"storageConfigInfo\":{\"storageType\":\"FILE\",\"allowedLocations\":[\"file://$WH\"]}}}"

curl -s -o /dev/null -w "grant          : HTTP %{http_code}\n" \
  -X PUT "$BASE/api/management/v1/catalogs/$CATALOG/catalog-roles/catalog_admin/grants" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"grant":{"type":"catalog","privilege":"CATALOG_MANAGE_CONTENT"}}'

curl -s -o /dev/null -w "role bind      : HTTP %{http_code}\n" \
  -X PUT "$BASE/api/management/v1/principal-roles/service_admin/catalog-roles/$CATALOG" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"catalogRole":{"name":"catalog_admin"}}'

echo "--- seeding control table ---"
python3 "$(dirname "$0")/seed_table.py" --catalog apache-polaris
echo
echo "control catalog ready. Run the harness with:"
echo "  export POLARIS_CLIENT_ID=root POLARIS_CLIENT_SECRET=s3cr3t"
echo "  python3 run.py --only apache-polaris --allow-writes"
