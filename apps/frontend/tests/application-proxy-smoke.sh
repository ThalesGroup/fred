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
FRONTEND_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEST_DIR=$(mktemp -d)
trap 'rm -rf "${TEST_DIR}"' EXIT HUP INT TERM
mkdir "${TEST_DIR}/bin"
printf '#!/bin/sh\nexit 0\n' > "${TEST_DIR}/bin/nginx"
chmod +x "${TEST_DIR}/bin/nginx"
export PATH="${TEST_DIR}/bin:${PATH}"
export FRONTEND_NGINX_CONFIG="${TEST_DIR}/fred.conf"
export FRONTEND_THEME_OVERLAY_SCRIPT=/dev/null
export FRONTEND_CONTROL_PLANE_UPSTREAM=http://control-plane.invalid:8222
sh "${FRONTEND_DIR}/dockerfiles/docker-entrypoint.sh"
for expected in 'location ^~ /apps/' 'location ^~ /app-services/' 'proxy_pass $fred_control_plane_upstream;' 'proxy_request_buffering off;' 'proxy_buffering off;' 'proxy_read_timeout 3600;' 'proxy_send_timeout 3600;' 'client_max_body_size 10m;' 'log_format fred_json escape=json'; do
    grep -F "$expected" "$FRONTEND_NGINX_CONFIG" >/dev/null
done
! grep -E 'fred_application_|rewrite |FRONTEND_APPLICATIONS_JSON' "$FRONTEND_NGINX_CONFIG"
for key in FRONTEND_APPLICATIONS_JSON FRONTEND_ENABLE_APPLICATIONS; do
    if env "$key=[]" sh "${FRONTEND_DIR}/dockerfiles/docker-entrypoint.sh" >"${TEST_DIR}/error" 2>&1; then
        echo "Retired $key unexpectedly accepted" >&2
        exit 1
    fi
    grep -F 'Admin > Applications' "${TEST_DIR}/error" >/dev/null
done
if FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE=10mb sh "${FRONTEND_DIR}/dockerfiles/docker-entrypoint.sh" >/dev/null 2>&1; then
    exit 1
fi
echo "Application gateway configuration checks passed"
