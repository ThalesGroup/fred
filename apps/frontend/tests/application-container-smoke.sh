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
[ -n "$image" ] || { echo 'Set FRONTEND_IMAGE to an already-built frontend image' >&2; exit 2; }
docker image inspect "$image" >/dev/null
test_directory=$(mktemp -d)
network="fred-gateway-smoke-$$"
upstream="fred-gateway-upstream-$$"
frontend="fred-gateway-frontend-$$"
cleanup() {
    docker rm -f "$frontend" "$upstream" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    rm -rf "$test_directory"
}
trap cleanup EXIT HUP INT TERM
cat > "${test_directory}/upstream.conf" <<'EOF'
pid /tmp/nginx.pid;
error_log /dev/stderr notice;
events {}
http {
    access_log /dev/stdout;
    # Emit a bounded marker: raw multipart bodies contain CRLF and cannot be
    # echoed safely in the existing single-line body header below.
    map $request_body $manager_body_received {
        default 0;
        ~manager-zip-probe 1;
    }
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
            add_header X-Smoke-Manager-Body $manager_body_received always;
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

docker network create "$network" >/dev/null
docker run -d --rm --network "$network" --name "$upstream" --entrypoint nginx \
    -v "$test_directory/upstream.conf:/tmp/upstream.conf:ro" "$image" \
    -c /tmp/upstream.conf -g 'daemon off;' >/dev/null
docker run -d --network "$network" --name "$frontend" -p 127.0.0.1::8080 \
    -e "FRONTEND_CONTROL_PLANE_UPSTREAM=http://${upstream}:8080" "$image" >/dev/null
port=$(docker port "$frontend" 8080/tcp | sed -n '1s/.*://p')
attempt=0
until curl -fsS "http://127.0.0.1:${port}/" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 40 ]; then docker logs "$frontend"; exit 1; fi
    sleep 0.25
done
# Exact paths and credentials reach Control Plane, including encoded request data.
for path in '/apps/evaluation/assets/main.mjs?v=1' '/app-services/evaluation/spaces/a?x=a%20b' '/apps/evaluation/x%0D%0AX-Injected:%20yes%0D%0A'; do
    status=$(curl --path-as-is -sS -D "$test_directory/headers" -o /dev/null -w '%{http_code}' \
        -H 'Authorization: Bearer smoke' "http://127.0.0.1:${port}${path}")
    [ "$status" = 204 ]
    grep -i -F "X-Smoke-Request-Uri: ${path}" "$test_directory/headers" >/dev/null
    grep -i -F 'X-Smoke-Authorization: Bearer smoke' "$test_directory/headers" >/dev/null
    ! grep -i '^X-Injected:' "$test_directory/headers"
done
status=$(curl -sS -D "$test_directory/headers" -o /dev/null -w '%{http_code}' \
    -H 'Authorization: Bearer smoke' -F 'file=manager-zip-probe' \
    "http://127.0.0.1:${port}/app-services/evaluation/spaces/a/upload")
[ "$status" = 204 ]
grep -i -F 'X-Smoke-Manager-Body: 1' "$test_directory/headers" >/dev/null
grep -i -F 'X-Smoke-Method: POST' "$test_directory/headers" >/dev/null
for path in /apps /app-services; do
    [ "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}${path}")" = 404 ]
done
echo 'Application container gateway checks passed'
