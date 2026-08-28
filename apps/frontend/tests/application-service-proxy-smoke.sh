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

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FRONTEND_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)
TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/fred-app-proxy.XXXXXX")
trap 'rm -rf "${TEST_DIR}"' EXIT HUP INT TERM

mkdir -p "${TEST_DIR}/bin"
cat > "${TEST_DIR}/bin/nginx" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod +x "${TEST_DIR}/bin/nginx"

write_contract() {
    contract_path=$1
    cat > "${contract_path}" <<'EOF'
{
  "schema_version": "1",
  "catalog_revision": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "applications": [
    { "id": "optional-app", "service_required": false },
    { "id": "required-app", "service_required": true }
  ]
}
EOF
}

run_entrypoint() {
    contract_path=$1
    config_path=$2
    mappings=$3
    enabled=$4
    client_max_body_size=${5-}
    PATH="${TEST_DIR}/bin:${PATH}" \
        FRONTEND_ENABLE_APPLICATIONS="${enabled}" \
        FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE="${client_max_body_size}" \
        FRONTEND_APPLICATION_RUNTIME_CONTRACT="${contract_path}" \
        FRONTEND_APPLICATION_UPSTREAMS_JSON="${mappings}" \
        FRONTEND_NGINX_CONFIG="${config_path}" \
        FRONTEND_DNS_RESOLVER="127.0.0.11" \
        sh "${FRONTEND_DIR}/dockerfiles/docker-entrypoint.sh"
}

run_entrypoint_with_default_flag() {
    contract_path=$1
    config_path=$2
    mappings=$3
    (
        unset FRONTEND_ENABLE_APPLICATIONS
        PATH="${TEST_DIR}/bin:${PATH}" \
            FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE='not-a-size' \
            FRONTEND_APPLICATION_RUNTIME_CONTRACT="${contract_path}" \
            FRONTEND_APPLICATION_UPSTREAMS_JSON="${mappings}" \
            FRONTEND_NGINX_CONFIG="${config_path}" \
            FRONTEND_DNS_RESOLVER="127.0.0.11" \
            sh "${FRONTEND_DIR}/dockerfiles/docker-entrypoint.sh"
    )
}

assert_contains() {
    path=$1
    expected=$2
    if ! grep -F -- "${expected}" "${path}" >/dev/null; then
        echo "Expected ${path} to contain: ${expected}" >&2
        exit 1
    fi
}

assert_not_contains() {
    path=$1
    unexpected=$2
    if grep -F -- "${unexpected}" "${path}" >/dev/null; then
        echo "Expected ${path} not to contain: ${unexpected}" >&2
        exit 1
    fi
}

assert_contains "${FRONTEND_DIR}/dockerfiles/Dockerfile-prod" 'apk add --no-cache ca-certificates jq'
assert_contains \
    "${FRONTEND_DIR}/dockerfiles/Dockerfile-prod" \
    '/workspace/apps/frontend/generated/application-runtime.json /etc/fred/application-runtime.json'
assert_contains \
    "${FRONTEND_DIR}/dockerfiles/Dockerfile-prod" \
    'COPY apps/applications/ /workspace/apps/applications/'

contract="${TEST_DIR}/application-runtime.json"
config="${TEST_DIR}/fred.conf"
write_contract "${contract}"

# The kill switch defaults off, returns 404 for the whole gateway namespace,
# and does not inspect unused application contracts or mappings.
disabled_config="${TEST_DIR}/fred-disabled.conf"
run_entrypoint_with_default_flag \
    "${TEST_DIR}/missing-application-runtime.json" \
    "${disabled_config}" \
    'not-json'
assert_contains "${disabled_config}" 'location = /app-services {'
assert_contains "${disabled_config}" 'location ^~ /app-services/ {'
assert_not_contains "${disabled_config}" 'fred_application_installed'
assert_not_contains "${disabled_config}" 'proxy_pass $fred_application_upstream'

if run_entrypoint "${contract}" "${config}" '{}' 'TRUE' >/dev/null 2>&1; then
    echo "Invalid application feature flag unexpectedly passed validation" >&2
    exit 1
fi

if run_entrypoint \
    "${contract}" \
    "${config}" \
    '{"required-app":"http://required.invalid"}' \
    'true' \
    '10mb' >/dev/null 2>&1; then
    echo "Invalid application client body size unexpectedly passed validation" >&2
    exit 1
fi

run_entrypoint \
    "${FRONTEND_DIR}/generated/application-runtime.json" \
    "${config}" \
    '{}' \
    'true'

run_entrypoint \
    "${contract}" \
    "${config}" \
    '{"required-app":"https://required.invalid:8443/root///","optional-app":"http://optional.invalid///"}' \
    'true'

assert_contains "${config}" '"required-app" "https://required.invalid:8443/root";'
assert_contains "${config}" '"optional-app" "http://optional.invalid";'
assert_contains "${config}" '"required-app" "required.invalid:8443";'
assert_contains "${config}" '"required-app" "required.invalid";'
assert_contains "${config}" '"required-app" 1;'
assert_contains "${config}" 'default 0;'
assert_contains "${config}" 'return 404;'
assert_contains "${config}" 'return 503;'
assert_contains "${config}" 'proxy_pass $fred_application_upstream$fred_application_path$is_args$args;'
assert_contains "${config}" 'client_max_body_size 10m;'
assert_contains "${config}" 'proxy_request_buffering off;'
assert_contains "${config}" 'proxy_set_header Host $fred_application_upstream_authority;'
assert_contains "${config}" 'proxy_ssl_server_name on;'
assert_contains "${config}" 'proxy_ssl_name $fred_application_upstream_server_name;'
assert_contains "${config}" 'proxy_ssl_verify on;'
assert_contains "${config}" 'proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;'
assert_contains "${config}" 'proxy_ssl_verify_depth 5;'

# Optional services may have no mapping; nginx configuration and Fred shell
# startup still succeed, while requests to the installed id return 503.
run_entrypoint "${contract}" "${config}" '{"required-app":"http://required.invalid"}' 'true'
if grep -F -- '"optional-app" "http://' "${config}" >/dev/null; then
    echo "Optional application unexpectedly received an upstream mapping" >&2
    exit 1
fi

if run_entrypoint "${contract}" "${config}" '{}' 'true' >/dev/null 2>&1; then
    echo "Missing required application upstream unexpectedly passed validation" >&2
    exit 1
fi

if run_entrypoint \
    "${contract}" \
    "${config}" \
    '{"required-app":"http://required.invalid","unknown-app":"http://unknown.invalid"}' \
    'true' >/dev/null 2>&1; then
    echo "Uninstalled application upstream unexpectedly passed validation" >&2
    exit 1
fi

if run_entrypoint \
    "${contract}" \
    "${config}" \
    '{"required-app":"http://required.invalid/$unsafe"}' \
    'true' >/dev/null 2>&1; then
    echo "Unsafe application upstream unexpectedly passed validation" >&2
    exit 1
fi

if run_entrypoint \
    "${contract}" \
    "${config}" \
    '{"required-app":"http://required.invalid/root/../private"}' \
    'true' >/dev/null 2>&1; then
    echo "Application upstream path traversal unexpectedly passed validation" >&2
    exit 1
fi

if run_entrypoint \
    "${contract}" \
    "${config}" \
    '{"required-app":"http://required.invalid/%2e%2e/private"}' \
    'true' >/dev/null 2>&1; then
    echo "Encoded application upstream path unexpectedly passed validation" >&2
    exit 1
fi

echo "Application service proxy smoke checks passed"
