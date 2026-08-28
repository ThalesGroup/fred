#!/bin/sh
# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -eu

image=${FRONTEND_IMAGE:-${1:-}}
if [ -z "${image}" ]; then
    echo "Set FRONTEND_IMAGE to an already-built Fred frontend image" >&2
    exit 2
fi
if ! command -v docker >/dev/null 2>&1 || \
    ! command -v curl >/dev/null 2>&1 || \
    ! command -v openssl >/dev/null 2>&1; then
    echo "The frontend container smoke test requires docker, curl, and openssl" >&2
    exit 2
fi
if ! docker image inspect "${image}" >/dev/null 2>&1; then
    echo "Frontend image is not available locally: ${image}" >&2
    exit 2
fi

test_directory=$(mktemp -d "${TMPDIR:-/tmp}/fred-app-container.XXXXXX")
suffix=$$
network="fred-app-container-${suffix}"
upstream="fred-app-upstream-${suffix}"
disabled_frontend="fred-app-disabled-${suffix}"
frontend="fred-app-frontend-${suffix}"
unhealthy_frontend="fred-app-unhealthy-${suffix}"
tls_upstream="fred-app-tls-upstream-${suffix}"
tls_frontend="fred-app-tls-frontend-${suffix}"

cleanup() {
    docker rm -f \
        "${disabled_frontend}" \
        "${frontend}" \
        "${unhealthy_frontend}" \
        "${tls_frontend}" \
        "${tls_upstream}" \
        "${upstream}" >/dev/null 2>&1 || true
    docker network rm "${network}" >/dev/null 2>&1 || true
    rm -rf "${test_directory}"
}
trap cleanup EXIT HUP INT TERM

cat > "${test_directory}/upstream.conf" <<'EOF'
pid /tmp/nginx.pid;
error_log /dev/stderr notice;
events {}
http {
    access_log /dev/stdout;
    server {
        listen 8080;
        client_body_in_single_buffer on;
        location / {
            proxy_pass http://127.0.0.1:8081;
            add_header X-Smoke-Request-Uri $request_uri always;
            add_header X-Smoke-Host $http_host always;
            add_header X-Smoke-Method $request_method always;
            add_header X-Smoke-Authorization $http_authorization always;
            add_header X-Smoke-Metadata $http_x_smoke_metadata always;
            add_header X-Smoke-Body $request_body always;
        }
    }
    server {
        listen 8081;
        location / {
            return 204;
        }
    }
}
EOF

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
    -subj "/CN=${tls_upstream}" \
    -addext "subjectAltName=DNS:${tls_upstream}" \
    -keyout "${test_directory}/untrusted.key" \
    -out "${test_directory}/untrusted.crt" >/dev/null 2>&1
chmod 644 "${test_directory}/untrusted.key" "${test_directory}/untrusted.crt"

cat > "${test_directory}/tls-upstream.conf" <<EOF
pid /tmp/nginx.pid;
error_log /dev/stderr notice;
events {}
http {
    access_log /dev/stdout;
    server {
        listen 8443 ssl;
        ssl_certificate /tmp/untrusted.crt;
        ssl_certificate_key /tmp/untrusted.key;
        location / {
            return 204;
        }
    }
}
EOF

cat > "${test_directory}/application-runtime.json" <<'EOF'
{
  "schema_version": "1",
  "catalog_revision": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "applications": [
    { "id": "optional-app", "service_required": false },
    { "id": "required-app", "service_required": true }
  ]
}
EOF

docker network create "${network}" >/dev/null
docker run --rm --entrypoint test "${image}" -r /etc/ssl/certs/ca-certificates.crt
docker run -d --rm \
    --network "${network}" \
    --name "${upstream}" \
    --entrypoint nginx \
    -v "${test_directory}/upstream.conf:/tmp/upstream.conf:ro" \
    "${image}" \
    -c /tmp/upstream.conf -g 'daemon off;' >/dev/null
docker run -d --rm \
    --network "${network}" \
    --name "${tls_upstream}" \
    --entrypoint nginx \
    -v "${test_directory}/tls-upstream.conf:/tmp/tls-upstream.conf:ro" \
    -v "${test_directory}/untrusted.crt:/tmp/untrusted.crt:ro" \
    -v "${test_directory}/untrusted.key:/tmp/untrusted.key:ro" \
    "${image}" \
    -c /tmp/tls-upstream.conf -g 'daemon off;' >/dev/null

start_frontend() {
    container=$1
    mappings=$2
    enabled=$3
    # Keep failed frontends until cleanup so their startup logs remain
    # available to the diagnostic path in wait_for_shell.
    docker run -d \
        --network "${network}" \
        --name "${container}" \
        -p 127.0.0.1::8080 \
        -v "${test_directory}/application-runtime.json:/etc/fred/application-runtime.json:ro" \
        -e "FRONTEND_AGENTIC_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_CONTROL_PLANE_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_EVALUATION_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_ENABLE_APPLICATIONS=${enabled}" \
        -e "FRONTEND_APPLICATION_UPSTREAMS_JSON=${mappings}" \
        "${image}" >/dev/null
}

wait_for_shell() {
    container=$1
    port=$(docker port "${container}" 8080/tcp | sed -n '1s/.*://p')
    attempt=0
    while [ "${attempt}" -lt 40 ]; do
        if curl -fsS "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
            printf '%s' "${port}"
            return 0
        fi
        if ! docker inspect -f '{{.State.Running}}' "${container}" 2>/dev/null | grep -F true >/dev/null; then
            docker logs "${container}" >&2 || true
            return 1
        fi
        attempt=$((attempt + 1))
        sleep 0.25
    done
    docker logs "${container}" >&2 || true
    return 1
}

# Disabled is the default deployment posture. Even a required application can
# have no mapping, the Fred shell remains healthy, and the whole gateway
# namespace is indistinguishable from an unknown route.
start_frontend "${disabled_frontend}" '{}' 'false'
disabled_frontend_port=$(wait_for_shell "${disabled_frontend}")
disabled_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:${disabled_frontend_port}/app-services/required-app/teams/team-disabled")
[ "${disabled_status}" = "404" ]
if docker logs "${upstream}" 2>&1 | grep -F '/teams/team-disabled' >/dev/null; then
    echo "Disabled application gateway forwarded a request upstream" >&2
    exit 1
fi
docker rm -f "${disabled_frontend}" >/dev/null

start_frontend \
    "${frontend}" \
    "{\"required-app\":\"http://${upstream}:8080/base///\"}" \
    'true'
frontend_port=$(wait_for_shell "${frontend}")

status=$(curl -sS \
    -D "${test_directory}/headers" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/required-app/teams/team-a/items/one?view=full")
[ "${status}" = "204" ]
grep -i -F "X-Smoke-Request-Uri: /base/teams/team-a/items/one?view=full" \
    "${test_directory}/headers" >/dev/null
grep -i -F "X-Smoke-Host: ${upstream}:8080" "${test_directory}/headers" >/dev/null

post_status=$(curl -sS \
    -X POST \
    -H 'Authorization: Bearer placeholder-token' \
    -H 'Content-Type: text/plain' \
    -H 'X-Smoke-Metadata: placeholder' \
    --data-binary 'request-body' \
    -D "${test_directory}/post-headers" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/required-app/teams/team-a/commands")
[ "${post_status}" = "204" ]
grep -i -F 'X-Smoke-Request-Uri: /base/teams/team-a/commands' \
    "${test_directory}/post-headers" >/dev/null
grep -i -F 'X-Smoke-Method: POST' "${test_directory}/post-headers" >/dev/null
grep -i -F 'X-Smoke-Authorization: Bearer placeholder-token' \
    "${test_directory}/post-headers" >/dev/null
grep -i -F 'X-Smoke-Metadata: placeholder' "${test_directory}/post-headers" >/dev/null
grep -i -F 'X-Smoke-Body: request-body' "${test_directory}/post-headers" >/dev/null
if grep -i -F 'metadata' "${test_directory}/post-headers" | grep -i -F 'X-Smoke-Request-Uri' >/dev/null; then
    echo "Application gateway put request metadata in the upstream request URI" >&2
    exit 1
fi

dd if=/dev/zero of="${test_directory}/over-limit.bin" bs=1048576 count=10 2>/dev/null
printf 'x' >> "${test_directory}/over-limit.bin"
over_limit_status=$(curl -sS \
    -X POST \
    -H 'Authorization: Bearer placeholder-token' \
    -H 'Content-Type: application/octet-stream' \
    -H 'Expect:' \
    --data-binary "@${test_directory}/over-limit.bin" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/required-app/teams/team-a/over-limit-probe")
[ "${over_limit_status}" = "413" ]
if docker logs "${upstream}" 2>&1 | grep -F '/over-limit-probe' >/dev/null; then
    echo "Over-limit application request unexpectedly reached its upstream" >&2
    exit 1
fi

unknown_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/unknown-app/teams/team-a")
[ "${unknown_status}" = "404" ]
optional_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/optional-app/teams/team-a")
[ "${optional_status}" = "503" ]

docker rm -f "${frontend}" >/dev/null
start_frontend \
    "${unhealthy_frontend}" \
    "{\"required-app\":\"http://${upstream}:8080\",\"optional-app\":\"http://missing-service.invalid\"}" \
    'true'
wait_for_shell "${unhealthy_frontend}" >/dev/null

# Bearer-bearing application requests must never be forwarded across an
# unverified TLS connection. A self-signed upstream therefore fails with 502
# while the Fred shell remains healthy.
start_frontend \
    "${tls_frontend}" \
    "{\"required-app\":\"https://${tls_upstream}:8443\"}" \
    'true'
tls_frontend_port=$(wait_for_shell "${tls_frontend}")
tls_status=$(curl -sS \
    -H 'Authorization: Bearer placeholder-token' \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${tls_frontend_port}/app-services/required-app/teams/team-a")
[ "${tls_status}" = "502" ]

if docker run --rm \
    --network "${network}" \
    -v "${test_directory}/application-runtime.json:/etc/fred/application-runtime.json:ro" \
    -e "FRONTEND_AGENTIC_UPSTREAM=http://${upstream}:8080" \
    -e "FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://${upstream}:8080" \
    -e "FRONTEND_CONTROL_PLANE_UPSTREAM=http://${upstream}:8080" \
    -e "FRONTEND_EVALUATION_UPSTREAM=http://${upstream}:8080" \
    -e 'FRONTEND_ENABLE_APPLICATIONS=true' \
    -e 'FRONTEND_APPLICATION_UPSTREAMS_JSON={}' \
    "${image}" >/dev/null 2>&1; then
    echo "Frontend container accepted a missing required application upstream" >&2
    exit 1
fi

echo "Application-service container smoke checks passed"
