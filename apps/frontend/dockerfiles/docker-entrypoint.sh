#!/bin/sh
set -eu

# Why: `make docker-run` starts only the frontend container, so nginx must
# proxy backend routes instead of serving `index.html` for API requests.
# How: override FRONTEND_*_UPSTREAM with reachable backend base URLs when the
# defaults do not match your environment.
# Example:
#   FRONTEND_AGENTIC_UPSTREAM=http://host.docker.internal:8000 \
#   FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://host.docker.internal:8111 \
#   FRONTEND_CONTROL_PLANE_UPSTREAM=http://host.docker.internal:8222 \
#   FRONTEND_EVALUATION_UPSTREAM=http://host.docker.internal:8336 \
#   /usr/local/bin/fred-frontend-entrypoint.sh
# FRONTEND_DNS_RESOLVER overrides the resolver nginx uses for optional
# upstreams (default: the container's own nameserver, from /etc/resolv.conf,
# falling back to Docker's embedded DNS 127.0.0.11).
# FRONTEND_ENABLE_APPLICATIONS is the deployment-wide application gateway
# switch. It accepts only true or false and defaults to the fail-closed state.
# FRONTEND_APPLICATIONS_JSON registers the applications this deployment serves.
# Registration is deployment configuration, not a build artifact: each entry
# names an app_id, the fork-built UI behind /apps/<app_id>/, and optionally the
# application service behind /app-services/<app_id>/. Example:
#   FRONTEND_APPLICATIONS_JSON='[{"app_id":"acme-forecast",
#     "ui_upstream":"http://acme-forecast-ui:80",
#     "service_upstream":"http://acme-forecast-api:8000",
#     "service_required":true}]'
# FRONTEND_THEME_URL points at a zip laid out like apps/frontend/public/
# (images/, contrib/<brand>/, root *.md). Its files are served in place of the
# baked ones for those three surfaces only, so a deployment brands the stock
# image without rebuilding it. https:// (public, presigned, or an S3 object URL
# signed with FRONTEND_THEME_S3_ACCESS_KEY + FRONTEND_THEME_S3_SECRET_KEY in
# region FRONTEND_THEME_S3_REGION) or file:// for an archive mounted from a
# volume. FRONTEND_THEME_REQUIRED=true makes a fetch or unpack failure fatal;
# by default the container logs a warning and serves the stock assets.
: "${FRONTEND_AGENTIC_UPSTREAM:=http://fred-agents}"
: "${FRONTEND_KNOWLEDGE_FLOW_UPSTREAM:=http://knowledge-flow-backend:8000}"
: "${FRONTEND_CONTROL_PLANE_UPSTREAM:=http://control-plane-backend:8222}"
: "${FRONTEND_EVALUATION_UPSTREAM:=http://fred-evaluation-backend}"
: "${FRONTEND_CLIENT_MAX_BODY_SIZE:=150m}"
: "${FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE:=10m}"
: "${FRONTEND_NGINX_CONFIG:=/etc/nginx/conf.d/fred.conf}"
: "${FRONTEND_ENABLE_APPLICATIONS:=false}"
: "${FRONTEND_THEME_URL:=}"
: "${FRONTEND_THEME_S3_ACCESS_KEY:=}"
: "${FRONTEND_THEME_S3_SECRET_KEY:=}"
: "${FRONTEND_THEME_S3_REGION:=us-east-1}"
: "${FRONTEND_THEME_REQUIRED:=false}"
FRONTEND_THEME_DIR=/usr/share/nginx/html/theme
if [ -z "${FRONTEND_APPLICATIONS_JSON:-}" ]; then
    FRONTEND_APPLICATIONS_JSON='[]'
fi

fail_application_configuration() {
    echo "Invalid application configuration: $1" >&2
    exit 1
}

case "${FRONTEND_ENABLE_APPLICATIONS}" in
    true | false) ;;
    *) fail_application_configuration "FRONTEND_ENABLE_APPLICATIONS must be either true or false" ;;
esac

if [ "${FRONTEND_ENABLE_APPLICATIONS}" = "true" ]; then
    if ! printf '%s' "${FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE}" | grep -Eq '^[1-9][0-9]*[kKmMgG]?$'; then
        fail_application_configuration "FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE must be a positive nginx size"
    fi
    if ! command -v jq >/dev/null 2>&1; then
        fail_application_configuration "jq is required to validate application registrations"
    fi
    if ! printf '%s' "${FRONTEND_APPLICATIONS_JSON}" | jq -e '
        # Origin only. nginx forwards the client path verbatim to a proxy_pass
        # that carries no URI part, so a base path here would silently replace
        # the whole request path instead of prefixing it.
        def safe_url:
            type == "string" and
            test("^https?://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\\[[0-9A-Fa-f:]+\\])(?::(?:[0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?/*\\z");
        type == "array" and
        (all(.[];
            type == "object" and
            ((keys - ["app_id", "service_required", "service_upstream", "ui_upstream"]) | length == 0) and
            # \z, not $: $ also matches before a trailing newline, and such an
            # id lands in the maps below as an empty key answering for every
            # unregistered id. The four names are map-block directives, which
            # nginx reads as syntax wherever a key was meant.
            (.app_id | type == "string" and
                test("^[a-z][a-z0-9]*(?:-[a-z0-9]+)*\\z") and
                (IN("default", "hostnames", "include", "volatile") | not)) and
            (.ui_upstream | safe_url) and
            (.service_upstream == null or (.service_upstream | safe_url)) and
            ((.service_required // false) | type == "boolean") and
            ((.service_required // false) == false or .service_upstream != null)
        )) and
        ([.[].app_id] | length == (unique | length))
    ' >/dev/null 2>&1; then
        fail_application_configuration "FRONTEND_APPLICATIONS_JSON must list unique app_ids with a safe HTTP(S) ui_upstream, plus a service_upstream for every service_required application"
    fi
fi

case "${FRONTEND_THEME_REQUIRED}" in
    true | false) ;;
    *)
        echo "Invalid theme configuration: FRONTEND_THEME_REQUIRED must be either true or false" >&2
        exit 1
        ;;
esac

theme_failure() {
    if [ "${FRONTEND_THEME_REQUIRED}" = "true" ]; then
        echo "Theme installation failed: $1" >&2
        exit 1
    fi
    echo "Theme skipped, serving the stock assets: $1" >&2
}

# Fetch FRONTEND_THEME_URL and copy its served surfaces into the overlay
# directory. Symlinks are dropped: unzip recreates them and nginx would follow
# one out of the web root.
install_theme() {
    [ -n "${FRONTEND_THEME_URL}" ] || return 0
    work=$(mktemp -d /tmp/fred-theme.XXXXXX)
    archive="${work}/theme.zip"
    if [ -n "${FRONTEND_THEME_S3_ACCESS_KEY}" ] && [ -n "${FRONTEND_THEME_S3_SECRET_KEY}" ]; then
        # The credential goes through a private config file, never the command line.
        printf 'user = "%s:%s"\n' "${FRONTEND_THEME_S3_ACCESS_KEY}" "${FRONTEND_THEME_S3_SECRET_KEY}" > "${work}/curl.conf"
        set -- -K "${work}/curl.conf" --aws-sigv4 "aws:amz:${FRONTEND_THEME_S3_REGION}:s3"
    else
        set --
    fi
    if ! curl "$@" -fsSL --retry 2 --max-time 120 -o "${archive}" "${FRONTEND_THEME_URL}"; then
        rm -rf "${work}"
        theme_failure "cannot download ${FRONTEND_THEME_URL}"
        return 0
    fi
    # unzip relocates entries that escape the archive root and says so. Such an
    # archive is malformed: refuse it instead of guessing where its files go.
    if unzip -l "${archive}" 2>&1 | grep -q 'removing leading'; then
        rm -rf "${work}"
        theme_failure "archive contains entries escaping its root"
        return 0
    fi
    mkdir "${work}/unpacked"
    if ! unzip -oq "${archive}" -d "${work}/unpacked" >/dev/null 2>&1; then
        rm -rf "${work}"
        theme_failure "cannot unpack the archive"
        return 0
    fi
    find "${work}/unpacked" -type l -delete
    root="${work}/unpacked"
    # zip -r acme-theme/ wraps everything in one folder: look inside it.
    set -- "${root}"/*
    if [ $# -eq 1 ] && [ -d "$1" ]; then
        case "$(basename "$1")" in
            images | contrib) ;;
            *) root=$1 ;;
        esac
    fi
    staging="${work}/theme"
    mkdir "${staging}"
    for entry in "${root}"/*; do
        [ -e "${entry}" ] || continue
        name=$(basename "${entry}")
        if [ -d "${entry}" ] && { [ "${name}" = images ] || [ "${name}" = contrib ]; }; then
            cp -R "${entry}" "${staging}/"
        elif [ -f "${entry}" ] && [ "${name%.md}" != "${name}" ]; then
            cp "${entry}" "${staging}/"
        else
            echo "Theme entry ignored, not a served surface: ${name}" >&2
        fi
    done
    if ! mkdir -p "${FRONTEND_THEME_DIR}" ||
        ! find "${FRONTEND_THEME_DIR}" -mindepth 1 -delete ||
        ! cp -R "${staging}/." "${FRONTEND_THEME_DIR}/"; then
        rm -rf "${work}"
        theme_failure "cannot write ${FRONTEND_THEME_DIR}"
        return 0
    fi
    rm -rf "${work}"
    echo "Theme installed from ${FRONTEND_THEME_URL}: $(find "${FRONTEND_THEME_DIR}" -type f | wc -l | tr -d ' ') files"
}

install_theme

# fred-agent-evaluator is optional: some platforms don't deploy it, so
# FRONTEND_EVALUATION_UPSTREAM's hostname may not resolve. A literal
# proxy_pass target is resolved eagerly at nginx startup — an unresolvable
# host would then make nginx refuse to start at all ("host not found in
# upstream"), crash-looping the whole frontend instead of just leaving
# /evaluation/ unreachable. Resolving it as a variable at request time
# (via `resolver`) keeps startup independent of that upstream's presence.
if [ -z "${FRONTEND_DNS_RESOLVER:-}" ]; then
    FRONTEND_DNS_RESOLVER="$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf 2>/dev/null || true)"
fi
: "${FRONTEND_DNS_RESOLVER:=127.0.0.11}"

{
if [ "${FRONTEND_ENABLE_APPLICATIONS}" = "true" ]; then
# One id map serves both prefixes: the UI and the service of an application
# always share its id, and each location reads its own upstream map below.
printf 'map $uri $fred_application_id {\n'
printf '    default "";\n'
printf '    ~^/apps/(?<fred_ui_id_from_uri>[a-z][a-z0-9-]*)(?:/|$) $fred_ui_id_from_uri;\n'
printf '    ~^/app-services/(?<fred_service_id_from_uri>[a-z][a-z0-9-]*)(?:/|$) $fred_service_id_from_uri;\n'
printf '}\n\n'

printf 'map $fred_application_id $fred_application_installed {\n'
printf '    default 0;\n'
printf '%s' "${FRONTEND_APPLICATIONS_JSON}" |
    jq -r 'sort_by(.app_id)[] | .app_id' |
    while IFS= read -r application_id; do
        printf '    "%s" 1;\n' "${application_id}"
    done
printf '}\n\n'

# Emit one nginx map from application id to a projection of the named upstream
# field. Applications without that field simply fall through to the default.
emit_application_map() {
    map_variable=$1
    upstream_field=$2
    projection=$3
    printf 'map $fred_application_id $%s {\n' "${map_variable}"
    printf '    default "";\n'
    printf '%s' "${FRONTEND_APPLICATIONS_JSON}" |
        jq -r --arg field "${upstream_field}" --arg projection "${projection}" '
            def url_parts:
                capture("^https?://(?<host>\\[[0-9A-Fa-f:]+\\]|[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(?::(?<port>[0-9]+))?(?:/|$)");
            [.[] | select(.[$field] != null)] | sort_by(.app_id)[] |
            .[$field] as $url |
            ($url | url_parts) as $parts |
            (if $projection == "upstream" then ($url | sub("/+$"; ""))
             elif $projection == "authority" then ($parts.host + (if ($parts.port // "") == "" then "" else ":" + $parts.port end))
             else ($parts.host | ltrimstr("[") | rtrimstr("]"))
             end) as $value |
            "\(.app_id)|\($value)"
        ' |
        while IFS='|' read -r application_id application_value; do
            printf '    "%s" "%s";\n' "${application_id}" "${application_value}"
        done
    printf '}\n\n'
}

emit_application_map fred_application_upstream service_upstream upstream
emit_application_map fred_application_upstream_authority service_upstream authority
emit_application_map fred_application_upstream_server_name service_upstream server_name
emit_application_map fred_application_ui_upstream ui_upstream upstream
emit_application_map fred_application_ui_authority ui_upstream authority
emit_application_map fred_application_ui_server_name ui_upstream server_name
fi

cat <<EOF
server {
    listen 8080;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html index.htm;
    client_max_body_size ${FRONTEND_CLIENT_MAX_BODY_SIZE};
    resolver ${FRONTEND_DNS_RESOLVER} valid=10s;

    location /fred/agents/v2 {
        proxy_pass ${FRONTEND_AGENTIC_UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }

    location /knowledge-flow/ {
        proxy_pass ${FRONTEND_KNOWLEDGE_FLOW_UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /control-plane/ {
        proxy_pass ${FRONTEND_CONTROL_PLANE_UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /evaluation/ {
        set \$evaluation_upstream ${FRONTEND_EVALUATION_UPSTREAM};
        proxy_pass \$evaluation_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
EOF

if [ "${FRONTEND_ENABLE_APPLICATIONS}" = "true" ]; then
cat <<'EOF'
    location = /apps {
        return 404;
    }

    # ^~ so this beats the \.mjs$ regex location below: an app bundle serves its
    # own module assets, which must reach the app UI and not Fred's document root.
    location ^~ /apps/ {
        if ($fred_application_ui_upstream = "") {
            return 404;
        }
EOF
printf '        client_max_body_size %s;\n' "${FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE}"
cat <<'EOF'
        # The whole /apps/<id> prefix is kept upstream so the absolute asset URLs
        # the fork baked into its bundle keep resolving through this location.
        # nginx re-escapes the normalized URI only for a proxy_pass with no URI
        # part, and only once a rewrite has marked the URI changed. (?s) because
        # a decoded LF in $uri is the case this exists for, and . must cross it.
        rewrite ^(?s)(.*)$ $1 break;
        proxy_pass $fred_application_ui_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $fred_application_ui_authority;
        proxy_redirect $fred_application_ui_upstream/ /;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_ssl_server_name on;
        proxy_ssl_name $fred_application_ui_server_name;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
        proxy_ssl_verify_depth 5;
    }

    location = /app-services {
        return 404;
    }

    location ~ ^/app-services/[a-z][a-z0-9-]*(?:/.*)$ {
        if ($fred_application_installed = 0) {
            return 404;
        }
        if ($fred_application_upstream = "") {
            return 503;
        }
EOF
printf '        client_max_body_size %s;\n' "${FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE}"
cat <<'EOF'
        proxy_request_buffering off;
        # Both guards above read the id map before this rewrite changes $uri,
        # which is what keeps $fred_application_id pinned for the redirect below.
        rewrite ^(?s)/app-services/[a-z][a-z0-9-]*(/.*)$ $1 break;
        proxy_pass $fred_application_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host $fred_application_upstream_authority;
        proxy_redirect $fred_application_upstream/ /app-services/$fred_application_id/;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_ssl_server_name on;
        proxy_ssl_name $fred_application_upstream_server_name;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
        proxy_ssl_verify_depth 5;
        proxy_buffering off;
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }

    location /app-services/ {
        return 404;
    }
EOF
else
cat <<'EOF'
    location = /apps {
        return 404;
    }

    location ^~ /apps/ {
        return 404;
    }

    location = /app-services {
        return 404;
    }

    location ^~ /app-services/ {
        return 404;
    }
EOF
fi

cat <<'EOF'
    # Deployment theme: files unpacked under /theme shadow the baked ones for
    # these three surfaces only. index.html, config.json and the bundle never do.
    location ^~ /images/ {
        try_files /theme$uri $uri /index.html;
    }

    location ^~ /contrib/ {
        try_files /theme$uri $uri /index.html;
    }

    location ~ ^/[^/]+\.md$ {
        try_files /theme$uri $uri /index.html;
    }

    location ^~ /theme/ {
        return 404;
    }

    location / {
        try_files $uri /index.html;
    }

    # Ensure ES module workers (.mjs) are served with a JS MIME type.
    location ~ \.mjs$ {
        try_files $uri =404;
        default_type application/javascript;
        types {
            application/javascript                           mjs;
        }
    }
}
EOF
} > "${FRONTEND_NGINX_CONFIG}"

exec nginx -g 'daemon off;'
