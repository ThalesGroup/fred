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
        # Redirect under the path it was reached by, so the gateway's rewrite of
        # the Location has a browser-facing prefix to get wrong.
        location ~ /redirect-probe$ {
            return 301 http://$http_host$uri/moved/;
        }
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
    registrations=$2
    enabled=$3
    # Keep failed frontends until cleanup so their startup logs remain
    # available to the diagnostic path in wait_for_shell.
    docker run -d \
        --network "${network}" \
        --name "${container}" \
        -p 127.0.0.1::8080 \
        -e "FRONTEND_AGENTIC_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_CONTROL_PLANE_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_EVALUATION_UPSTREAM=http://${upstream}:8080" \
        -e "FRONTEND_ENABLE_APPLICATIONS=${enabled}" \
        -e "FRONTEND_APPLICATIONS_JSON=${registrations}" \
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

registrations() {
    ui_upstream=$1
    printf '[{"app_id":"optional-app","ui_upstream":"http://%s:8080"},{"app_id":"required-app","ui_upstream":"%s","service_upstream":"http://%s:8080","service_required":true}]' \
        "${upstream}" "${ui_upstream}" "${upstream}"
}

# Disabled is the default deployment posture. Even a required application can
# have no registration, the Fred shell remains healthy, and both application
# namespaces are indistinguishable from an unknown route.
start_frontend "${disabled_frontend}" '[]' 'false'
disabled_frontend_port=$(wait_for_shell "${disabled_frontend}")
for disabled_path in \
    "/app-services/required-app/teams/team-disabled" \
    "/apps/required-app/index-disabled.html"; do
    disabled_status=$(curl -sS -o /dev/null -w '%{http_code}' \
        "http://127.0.0.1:${disabled_frontend_port}${disabled_path}")
    [ "${disabled_status}" = "404" ]
done
if docker logs "${upstream}" 2>&1 | grep -E '/teams/team-disabled|index-disabled' >/dev/null; then
    echo "Disabled application gateway forwarded a request upstream" >&2
    exit 1
fi
docker rm -f "${disabled_frontend}" >/dev/null

start_frontend "${frontend}" "$(registrations "http://${upstream}:8080")" 'true'
frontend_port=$(wait_for_shell "${frontend}")

# The UI leg keeps the whole /apps/<id> prefix so the bundle's own absolute
# asset URLs resolve, and .mjs assets must reach the app rather than Fred's
# document root — that is what the ^~ location modifier buys.
for ui_path in "/apps/required-app/" "/apps/required-app/assets/entry.mjs?v=1"; do
    ui_status=$(curl -sS \
        -D "${test_directory}/ui-headers" \
        -o /dev/null \
        -w '%{http_code}' \
        "http://127.0.0.1:${frontend_port}${ui_path}")
    [ "${ui_status}" = "204" ]
    grep -i -F "X-Smoke-Request-Uri: ${ui_path}" "${test_directory}/ui-headers" >/dev/null
    grep -i -F "X-Smoke-Host: ${upstream}:8080" "${test_directory}/ui-headers" >/dev/null
done

# A percent-encoded CR or LF must stay percent-encoded in the upstream request
# line. Decoding it there lets any client append headers, and whole extra
# requests, to the connection the gateway opened on its behalf.
smuggle_status=$(curl -sS \
    -D "${test_directory}/smuggle-headers" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/apps/required-app/x%0D%0AX-Injected:%20yes%0D%0A")
[ "${smuggle_status}" = "204" ]
grep -i -F 'X-Smoke-Request-Uri: /apps/required-app/x%0D%0AX-Injected:%20yes%0D%0A' \
    "${test_directory}/smuggle-headers" >/dev/null
# Anchored: the echoed request URI itself contains the header name.
if grep -i '^X-Injected:' "${test_directory}/smuggle-headers" >/dev/null; then
    echo "Application gateway let a request path inject an upstream header" >&2
    exit 1
fi

# A decoded LF must not stop the UI leg normalizing. Without it the rewrite
# cannot match, nginx falls back to forwarding the raw request URI, and the
# dot segments it had already resolved reach the application unresolved.
normalized_status=$(curl -sS \
    -D "${test_directory}/normalized-headers" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/apps/required-app/a/%2e%2e/b%0Ac")
[ "${normalized_status}" = "204" ]
if ! grep -i -F 'X-Smoke-Request-Uri: /apps/required-app/b%0Ac' \
    "${test_directory}/normalized-headers" >/dev/null; then
    echo "Application gateway did not normalize a path carrying a decoded LF" >&2
    grep -i '^X-Smoke-Request-Uri:' "${test_directory}/normalized-headers" >&2
    exit 1
fi

# Neither leg may shorten the path it forwards. A trailing LF sits exactly where
# an unanchored $ ends a match, so a rewrite that does not cross it hands the
# application a path one character shorter than the client asked for.
for trailing_case in \
    "/apps/required-app/x%0A /apps/required-app/x%0A" \
    "/app-services/required-app/teams/team-a/x%0A /teams/team-a/x%0A"; do
    trailing_path=${trailing_case% *}
    expected_uri=${trailing_case#* }
    curl -sS -D "${test_directory}/trailing-headers" -o /dev/null \
        "http://127.0.0.1:${frontend_port}${trailing_path}" >/dev/null
    if ! grep -i -F "X-Smoke-Request-Uri: ${expected_uri}" \
        "${test_directory}/trailing-headers" >/dev/null; then
        echo "Application gateway altered the path of ${trailing_path}" >&2
        grep -i '^X-Smoke-Request-Uri:' "${test_directory}/trailing-headers" >&2
        exit 1
    fi
done

# The service leg decodes a bare CR even where a CRLF pair is refused.
service_smuggle_status=$(curl -sS \
    -D "${test_directory}/service-smuggle-headers" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/required-app/teams/team-a/x%0DX-Injected:%20yes")
[ "${service_smuggle_status}" = "204" ]
grep -i -F 'X-Smoke-Request-Uri: /teams/team-a/x%0DX-Injected:%20yes' \
    "${test_directory}/service-smuggle-headers" >/dev/null
if grep -i '^X-Injected:' "${test_directory}/service-smuggle-headers" >/dev/null; then
    echo "Application gateway let a service request path inject an upstream header" >&2
    exit 1
fi

# The application service is the only thing that can authorize a team scope, so
# the path it validates must be the path it decodes: one round of decoding here
# would hand it a prefix that parses differently than it reads.
double_encoded_status=$(curl -sS \
    -D "${test_directory}/double-encoded-headers" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/required-app/teams/team-a/%252e%252e%252fteams/team-b/secret")
[ "${double_encoded_status}" = "204" ]
grep -i -F 'X-Smoke-Request-Uri: /teams/team-a/%252e%252e%252fteams/team-b/secret' \
    "${test_directory}/double-encoded-headers" >/dev/null

# A redirect from either leg must land back on the browser-facing prefix and
# must not name the upstream the gateway dialled. The whole path is asserted,
# not a substring: a proxy_redirect that lost the application id still leaves
# "/moved/" intact while sending every redirect to a 404.
assert_redirect() {
    request_path=$1
    expected_location=$2
    redirect_status=$(curl -sS \
        -D "${test_directory}/redirect-headers" \
        -o /dev/null \
        -w '%{http_code}' \
        "http://127.0.0.1:${frontend_port}${request_path}")
    [ "${redirect_status}" = "301" ]
    # The origin is nginx's own absolute_redirect rewrite and carries the
    # container's listen port, not the mapped one; only the path is pinned.
    if ! grep -iE \
        "^Location:[[:space:]]*(https?://[^/]*)?${expected_location}[[:space:]]*$" \
        "${test_directory}/redirect-headers" >/dev/null; then
        echo "Application gateway did not redirect ${request_path} to ${expected_location}" >&2
        grep -i '^Location:' "${test_directory}/redirect-headers" >&2
        exit 1
    fi
    if grep -i -F "${upstream}:8080" "${test_directory}/redirect-headers" >/dev/null; then
        echo "Application gateway leaked its upstream authority in a redirect" >&2
        exit 1
    fi
}

assert_redirect "/apps/required-app/redirect-probe" \
    "/apps/required-app/redirect-probe/moved/"
assert_redirect "/app-services/required-app/teams/team-a/redirect-probe" \
    "/app-services/required-app/teams/team-a/redirect-probe/moved/"

unknown_ui_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/apps/unknown-app/index.html")
[ "${unknown_ui_status}" = "404" ]
bare_ui_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/apps")
[ "${bare_ui_status}" = "404" ]

status=$(curl -sS \
    -D "${test_directory}/headers" \
    -o /dev/null \
    -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/required-app/teams/team-a/items/one?view=full")
[ "${status}" = "204" ]
grep -i -F "X-Smoke-Request-Uri: /teams/team-a/items/one?view=full" \
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
grep -i -F 'X-Smoke-Request-Uri: /teams/team-a/commands' \
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
# A registered UI-only application is unavailable, not unknown.
optional_status=$(curl -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:${frontend_port}/app-services/optional-app/teams/team-a")
[ "${optional_status}" = "503" ]

docker rm -f "${frontend}" >/dev/null
start_frontend "${unhealthy_frontend}" \
    "[{\"app_id\":\"required-app\",\"ui_upstream\":\"http://missing-ui.invalid\",\"service_upstream\":\"http://${upstream}:8080\",\"service_required\":true}]" \
    'true'
wait_for_shell "${unhealthy_frontend}" >/dev/null

# Bearer-bearing application requests must never be forwarded across an
# unverified TLS connection. A self-signed upstream therefore fails with 502
# while the Fred shell remains healthy.
start_frontend "${tls_frontend}" \
    "[{\"app_id\":\"required-app\",\"ui_upstream\":\"https://${tls_upstream}:8443\",\"service_upstream\":\"https://${tls_upstream}:8443\",\"service_required\":true}]" \
    'true'
tls_frontend_port=$(wait_for_shell "${tls_frontend}")
for tls_path in "/app-services/required-app/teams/team-a" "/apps/required-app/"; do
    tls_status=$(curl -sS \
        -H 'Authorization: Bearer placeholder-token' \
        -o /dev/null \
        -w '%{http_code}' \
        "http://127.0.0.1:${tls_frontend_port}${tls_path}")
    [ "${tls_status}" = "502" ]
done

if docker run --rm \
    --network "${network}" \
    -e "FRONTEND_AGENTIC_UPSTREAM=http://${upstream}:8080" \
    -e "FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://${upstream}:8080" \
    -e "FRONTEND_CONTROL_PLANE_UPSTREAM=http://${upstream}:8080" \
    -e "FRONTEND_EVALUATION_UPSTREAM=http://${upstream}:8080" \
    -e 'FRONTEND_ENABLE_APPLICATIONS=true' \
    -e 'FRONTEND_APPLICATIONS_JSON=[{"app_id":"required-app","ui_upstream":"http://ui.invalid","service_required":true}]' \
    "${image}" >/dev/null 2>&1; then
    echo "Frontend container accepted a service_required application with no service upstream" >&2
    exit 1
fi

echo "Application container smoke checks passed"
