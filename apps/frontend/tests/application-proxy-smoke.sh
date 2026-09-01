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

REGISTRATIONS='[
  {"app_id":"optional-app","ui_upstream":"http://optional-ui.invalid///"},
  {"app_id":"required-app","ui_upstream":"https://required-ui.invalid:8443/ui///",
   "service_upstream":"https://required-api.invalid:8443/root///","service_required":true}
]'

run_entrypoint() {
    config_path=$1
    registrations=$2
    enabled=$3
    client_max_body_size=${4-}
    PATH="${TEST_DIR}/bin:${PATH}" \
        FRONTEND_ENABLE_APPLICATIONS="${enabled}" \
        FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE="${client_max_body_size}" \
        FRONTEND_APPLICATIONS_JSON="${registrations}" \
        FRONTEND_NGINX_CONFIG="${config_path}" \
        FRONTEND_DNS_RESOLVER="127.0.0.11" \
        sh "${FRONTEND_DIR}/dockerfiles/docker-entrypoint.sh"
}

run_entrypoint_with_default_flag() {
    config_path=$1
    registrations=$2
    (
        unset FRONTEND_ENABLE_APPLICATIONS
        PATH="${TEST_DIR}/bin:${PATH}" \
            FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE='not-a-size' \
            FRONTEND_APPLICATIONS_JSON="${registrations}" \
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

assert_rejected() {
    description=$1
    registrations=$2
    if run_entrypoint "${TEST_DIR}/rejected.conf" "${registrations}" 'true' >/dev/null 2>&1; then
        echo "${description} unexpectedly passed validation" >&2
        exit 1
    fi
}

assert_contains "${FRONTEND_DIR}/dockerfiles/Dockerfile-prod" 'apk add --no-cache ca-certificates jq'
# Registration is runtime configuration now: no build artifact may be baked in.
assert_not_contains "${FRONTEND_DIR}/dockerfiles/Dockerfile-prod" 'application-runtime.json'
assert_not_contains "${FRONTEND_DIR}/dockerfiles/Dockerfile-prod" 'apps/applications'

config="${TEST_DIR}/fred.conf"

# The kill switch defaults off, returns 404 for both namespaces, and never
# inspects the registration list.
disabled_config="${TEST_DIR}/fred-disabled.conf"
run_entrypoint_with_default_flag "${disabled_config}" 'not-json'
assert_contains "${disabled_config}" 'location = /apps {'
assert_contains "${disabled_config}" 'location ^~ /apps/ {'
assert_contains "${disabled_config}" 'location = /app-services {'
assert_contains "${disabled_config}" 'location ^~ /app-services/ {'
assert_not_contains "${disabled_config}" 'fred_application_installed'
assert_not_contains "${disabled_config}" 'proxy_pass $fred_application_upstream'
assert_not_contains "${disabled_config}" 'proxy_pass $fred_application_ui_upstream'

if run_entrypoint "${config}" "${REGISTRATIONS}" 'TRUE' >/dev/null 2>&1; then
    echo "Invalid application feature flag unexpectedly passed validation" >&2
    exit 1
fi

if run_entrypoint "${config}" "${REGISTRATIONS}" 'true' '10mb' >/dev/null 2>&1; then
    echo "Invalid application client body size unexpectedly passed validation" >&2
    exit 1
fi

run_entrypoint "${config}" '[]' 'true'
run_entrypoint "${config}" "${REGISTRATIONS}" 'true'

# Both legs of every registration reach nginx, with normalized upstream roots.
assert_contains "${config}" '"required-app" "https://required-api.invalid:8443/root";'
assert_contains "${config}" '"required-app" "required-api.invalid:8443";'
assert_contains "${config}" '"required-app" "required-api.invalid";'
assert_contains "${config}" '"required-app" "https://required-ui.invalid:8443/ui";'
assert_contains "${config}" '"optional-app" "http://optional-ui.invalid";'
assert_contains "${config}" '"required-app" 1;'
assert_contains "${config}" '"optional-app" 1;'
assert_contains "${config}" 'default 0;'

# A plain-prefix /apps/ location would lose the app bundle's own .mjs assets to
# the regex location further down the file, so the ^~ modifier is load-bearing.
assert_contains "${config}" 'location ^~ /apps/ {'
assert_contains "${config}" 'proxy_pass $fred_application_ui_upstream$uri$is_args$args;'
assert_contains "${config}" 'proxy_set_header Host $fred_application_ui_authority;'
assert_contains "${config}" 'proxy_ssl_name $fred_application_ui_server_name;'

assert_contains "${config}" 'return 404;'
assert_contains "${config}" 'return 503;'
assert_contains "${config}" 'proxy_pass $fred_application_upstream$fred_application_path$is_args$args;'
assert_contains "${config}" 'client_max_body_size 10m;'
assert_contains "${config}" 'proxy_request_buffering off;'
assert_contains "${config}" 'proxy_set_header Host $fred_application_upstream_authority;'
assert_contains "${config}" 'proxy_ssl_server_name on;'
assert_contains "${config}" 'proxy_ssl_verify on;'
assert_contains "${config}" 'proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;'
assert_contains "${config}" 'proxy_ssl_verify_depth 5;'

# A UI-only application renders no service upstream, so its /app-services
# requests hit the 503 branch instead of being forwarded anywhere.
assert_not_contains "${config}" '"optional-app" "http://optional-api'

assert_rejected "Missing required service upstream" \
    '[{"app_id":"required-app","ui_upstream":"http://ui.invalid","service_required":true}]'
assert_rejected "Missing ui_upstream" \
    '[{"app_id":"required-app","service_upstream":"http://api.invalid"}]'
assert_rejected "Duplicate application id" \
    '[{"app_id":"app","ui_upstream":"http://ui.invalid"},{"app_id":"app","ui_upstream":"http://ui2.invalid"}]'
assert_rejected "Unsupported registration key" \
    '[{"app_id":"app","ui_upstream":"http://ui.invalid","module_key":"app"}]'
assert_rejected "Object instead of registration list" \
    '{"app":"http://ui.invalid"}'
assert_rejected "Non-boolean service_required" \
    '[{"app_id":"app","ui_upstream":"http://ui.invalid","service_required":"true"}]'

for unsafe in \
    'file:///tmp/service' \
    'http://service.invalid/path?parameter=value' \
    'http://service.invalid/$unsafe' \
    'http://service.invalid:99999' \
    'http://service.invalid/root/../private' \
    'http://service.invalid/%2e%2e/private'; do
    assert_rejected "Unsafe ui_upstream ${unsafe}" \
        "[{\"app_id\":\"app\",\"ui_upstream\":\"${unsafe}\"}]"
    assert_rejected "Unsafe service_upstream ${unsafe}" \
        "[{\"app_id\":\"app\",\"ui_upstream\":\"http://ui.invalid\",\"service_upstream\":\"${unsafe}\"}]"
done

echo "Application proxy smoke checks passed"
