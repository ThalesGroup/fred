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

# Exercises the deployment theme overlay of an already-built frontend image:
# archives served by a sidecar store, S3 signing, refused archives, and both
# failure modes. python3 builds the archives so no zip binary is needed.

set -eu

image=${FRONTEND_IMAGE:-${1:-}}
if [ -z "${image}" ]; then
    echo "Set FRONTEND_IMAGE to an already-built Fred frontend image" >&2
    exit 2
fi
if ! command -v docker >/dev/null 2>&1 || \
    ! command -v curl >/dev/null 2>&1 || \
    ! command -v python3 >/dev/null 2>&1; then
    echo "The theme container smoke test requires docker, curl, and python3" >&2
    exit 2
fi
if ! docker image inspect "${image}" >/dev/null 2>&1; then
    echo "Frontend image is not available locally: ${image}" >&2
    exit 2
fi

test_directory=$(mktemp -d "${TMPDIR:-/tmp}/fred-theme-container.XXXXXX")
suffix=$$
network="fred-theme-network-${suffix}"
store="fred-theme-store-${suffix}"
frontend="fred-theme-frontend-${suffix}"
refused="fred-theme-refused-${suffix}"

cleanup() {
    docker rm -f "${frontend}" "${refused}" "${store}" >/dev/null 2>&1 || true
    docker network rm "${network}" >/dev/null 2>&1 || true
    rm -rf "${test_directory}"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "${test_directory}/themes"
python3 - "${test_directory}/themes" <<'EOF'
import sys
import zipfile

out = sys.argv[1]
with zipfile.ZipFile(f"{out}/theme.zip", "w") as z:
    z.writestr("images/fred.svg", "<svg>theme-logo</svg>")
    z.writestr("images/acme-logo.svg", "<svg>acme-logo</svg>")
    z.writestr("images/icons/customAgent.svg", "<svg>acme-agent</svg>")
    z.writestr("gcu.md", "# theme terms")
    z.writestr("contrib/acme/release.md", "# acme release")
    # Never served from a theme, whatever the archive says.
    z.writestr("index.html", "<!doctype html>theme-shell")
    z.writestr("config.json", '{"theme":"shell"}')
    z.writestr("assets/theme.js", "theme-bundle")
    link = zipfile.ZipInfo("images/link.svg")
    link.external_attr = 0o120777 << 16
    z.writestr(link, "../../../../etc/passwd")
    # Stored with no permission bits at all: the entrypoint must still serve it.
    locked = zipfile.ZipInfo("images/locked.svg")
    locked.external_attr = 0o100000 << 16
    z.writestr(locked, "<svg>locked</svg>")
# A folder compressed from the macOS Finder: one wrapper folder plus __MACOSX.
with zipfile.ZipFile(f"{out}/wrapped.zip", "w") as z:
    z.writestr("acme-theme/images/fred.svg", "<svg>wrapped-logo</svg>")
    z.writestr("acme-theme/gdpr.md", "# wrapped privacy")
    z.writestr("__MACOSX/acme-theme/images/._fred.svg", "finder metadata")
with zipfile.ZipFile(f"{out}/escaping.zip", "w") as z:
    z.writestr("images/../../escape.svg", "<svg>escape</svg>")
    z.writestr("images/fred.svg", "<svg>escape-logo</svg>")
with zipfile.ZipFile(f"{out}/no-surfaces.zip", "w") as z:
    z.writestr("README.txt", "nothing nginx would serve")
with open(f"{out}/not-a-zip.zip", "w") as f:
    f.write("<html>bucket error page</html>")
EOF
# The store runs as nginx (uid 101) and must read files created by this user.
chmod -R a+rX "${test_directory}"

# The store logs the Authorization header so the S3 signing path can be
# asserted without a real S3 endpoint.
cat > "${test_directory}/store.conf" <<'EOF'
pid /tmp/nginx.pid;
error_log /dev/stderr notice;
events {}
http {
    log_format signing '$request_uri authorization="$http_authorization"';
    access_log /dev/stdout signing;
    server {
        listen 8080;
        root /tmp/themes;
    }
}
EOF

docker network create "${network}" >/dev/null
docker run -d --rm \
    --network "${network}" \
    --name "${store}" \
    --entrypoint nginx \
    -v "${test_directory}/store.conf:/tmp/store.conf:ro" \
    -v "${test_directory}/themes:/tmp/themes:ro" \
    "${image}" \
    -c /tmp/store.conf -g 'daemon off;' >/dev/null

frontend_args() {
    printf -- '--network %s ' "${network}"
    for upstream in AGENTIC KNOWLEDGE_FLOW CONTROL_PLANE EVALUATION; do
        printf -- '-e FRONTEND_%s_UPSTREAM=http://%s:8080 ' "${upstream}" "${store}"
    done
}

wait_until_stopped() {
    attempt=0
    while [ "${attempt}" -lt 80 ]; do
        if ! docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null | grep -F true >/dev/null; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 0.25
    done
    return 1
}

# Kept (no --rm) so a failed start still has logs for the diagnostic path.
start_frontend() {
    docker rm -f "${frontend}" >/dev/null 2>&1 || true
    # shellcheck disable=SC2046
    docker run -d --name "${frontend}" -p 127.0.0.1::8080 $(frontend_args) "$@" "${image}" >/dev/null
    attempt=0
    while [ "${attempt}" -lt 80 ]; do
        port=$(docker port "${frontend}" 8080/tcp 2>/dev/null | sed -n '1s/.*://p')
        if [ -n "${port}" ] && curl -fsS "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
            return 0
        fi
        if ! docker inspect -f '{{.State.Running}}' "${frontend}" 2>/dev/null | grep -F true >/dev/null; then
            docker logs "${frontend}" >&2 || true
            echo "Frontend container stopped before serving" >&2
            exit 1
        fi
        attempt=$((attempt + 1))
        sleep 0.25
    done
    docker logs "${frontend}" >&2 || true
    echo "Frontend container never became ready" >&2
    exit 1
}

# The container must stop on its own with the expected message; a container
# that keeps serving is a failure, not a hang.
expect_refused_start() {
    message=$1
    shift
    docker rm -f "${refused}" >/dev/null 2>&1 || true
    # shellcheck disable=SC2046
    docker run -d --name "${refused}" $(frontend_args) "$@" "${image}" >/dev/null
    if ! wait_until_stopped "${refused}"; then
        echo "Frontend container started although it should have refused: $*" >&2
        exit 1
    fi
    if ! docker logs "${refused}" 2>&1 | grep -qF "${message}"; then
        docker logs "${refused}" >&2 || true
        echo "Expected the refused container to say: ${message}" >&2
        exit 1
    fi
    docker rm -f "${refused}" >/dev/null 2>&1 || true
}

body() {
    curl -sS "http://127.0.0.1:${port}$1"
}

status() {
    curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}$1"
}

expect_status() {
    actual=$(status "$1")
    if [ "${actual}" != "$2" ]; then
        echo "Expected $1 to answer $2, got ${actual}" >&2
        exit 1
    fi
}

expect_body() {
    actual=$(body "$1")
    case "${actual}" in
        *"$2"*) ;;
        *)
            echo "Expected $1 to contain '$2', got: ${actual}" >&2
            exit 1
            ;;
    esac
}

refute_body() {
    actual=$(body "$1")
    case "${actual}" in
        *"$2"*)
            echo "Expected $1 not to contain '$2'" >&2
            exit 1
            ;;
    esac
}

expect_log() {
    if ! docker logs "${frontend}" 2>&1 | grep -qF "$1"; then
        docker logs "${frontend}" >&2 || true
        echo "Expected the frontend log to mention: $1" >&2
        exit 1
    fi
}

expect_store_log() {
    if ! docker logs "${store}" 2>&1 | grep -qF "$1"; then
        docker logs "${store}" >&2 || true
        echo "Expected the store log to mention: $1" >&2
        exit 1
    fi
}

theme_url="http://${store}:8080"

# No theme configured: stock assets, real 404 for a missing asset, and the SPA
# fallback still answers application routes.
start_frontend
stock_logo=$(body /images/fred.svg)
stock_terms=$(body /gcu.md)
expect_body /images/fred.svg '<svg'
refute_body /images/fred.svg theme-logo
refute_body /gcu.md 'theme terms'
expect_status /images/missing.svg 404
expect_status /contrib/none/release.md 404
expect_status /missing.md 404
expect_status /teams 200
body /teams | grep -qi '<!doctype'

# Full theme over a signed request: the served surfaces are overridden, the
# shell, its config and its bundle are not, the symlink is dropped, and the
# unreadable entry is served anyway. The quote in the key must reach the store
# intact through curl's config file.
start_frontend \
    -e "FRONTEND_THEME_URL=${theme_url}/theme.zip?X-Amz-Signature=not-for-the-logs" \
    -e 'FRONTEND_THEME_S3_ACCESS_KEY=theme"key' \
    -e 'FRONTEND_THEME_S3_SECRET_KEY=theme-secret'
expect_body /images/fred.svg theme-logo
expect_body /images/acme-logo.svg acme-logo
expect_body /images/icons/customAgent.svg acme-agent
expect_body /images/locked.svg locked
expect_body /gcu.md 'theme terms'
expect_body /contrib/acme/release.md 'acme release'
refute_body / theme-shell
refute_body /config.json '"theme"'
refute_body /assets/theme.js theme-bundle
refute_body /images/link.svg 'root:'
expect_status /images/link.svg 404
expect_log "Theme installed from ${theme_url}/theme.zip: "
expect_log 'ignored, not a served surface: index.html'
if docker logs "${frontend}" 2>&1 | grep -qF 'X-Amz-Signature'; then
    echo "The theme URL query string leaked into the frontend log" >&2
    exit 1
fi
# nginx serves public files; it must not keep the store credential.
if docker exec "${frontend}" sh -c "tr '\\0' '\\n' < /proc/1/environ" |
    grep -q '^FRONTEND_THEME_S3_SECRET_KEY='; then
    echo "The theme store credential survived into the nginx environment" >&2
    exit 1
fi
# nginx escapes the quote as \x22 in its access log.
expect_store_log '/theme.zip?X-Amz-Signature=not-for-the-logs authorization="AWS4-HMAC-SHA256 Credential=theme\x22key/'

# An archive made from a folder is unwrapped; without keys the request is anonymous.
start_frontend -e "FRONTEND_THEME_URL=${theme_url}/wrapped.zip"
expect_body /images/fred.svg wrapped-logo
expect_body /gdpr.md 'wrapped privacy'
[ "$(body /gcu.md)" = "${stock_terms}" ]
expect_store_log '/wrapped.zip authorization="-"'

# The same archive mounted from a volume, the ConfigMap or docker-compose path.
start_frontend \
    -v "${test_directory}/themes/theme.zip:/tmp/theme.zip:ro" \
    -e 'FRONTEND_THEME_URL=file:///tmp/theme.zip'
expect_body /gcu.md 'theme terms'

# Refused, empty or unreachable archives keep the stock look by default...
for broken in \
    "escaping.zip|archive contains entries with '..' or absolute paths" \
    "no-surfaces.zip|archive holds no images/, contrib/ or root markdown" \
    "not-a-zip.zip|cannot unpack the archive" \
    "missing.zip|cannot download"; do
    archive=${broken%%|*}
    message=${broken#*|}
    start_frontend -e "FRONTEND_THEME_URL=${theme_url}/${archive}"
    [ "$(body /images/fred.svg)" = "${stock_logo}" ]
    expect_log "Theme skipped, serving the stock assets: ${message}"
done

# ...and stop the container when the theme is required.
expect_refused_start "Theme installation failed: archive contains entries with '..' or absolute paths" \
    -e "FRONTEND_THEME_URL=${theme_url}/escaping.zip" -e 'FRONTEND_THEME_REQUIRED=true'
expect_refused_start "Theme installation failed: archive holds no images/, contrib/ or root markdown" \
    -e "FRONTEND_THEME_URL=${theme_url}/no-surfaces.zip" -e 'FRONTEND_THEME_REQUIRED=true'
expect_refused_start "Theme installation failed: cannot download" \
    -e "FRONTEND_THEME_URL=${theme_url}/missing.zip" -e 'FRONTEND_THEME_REQUIRED=true'
expect_refused_start "FRONTEND_THEME_REQUIRED must be either true or false" \
    -e 'FRONTEND_THEME_REQUIRED=maybe'

echo "Theme container smoke checks passed"
