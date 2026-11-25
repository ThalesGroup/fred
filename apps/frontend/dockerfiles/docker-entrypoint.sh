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

# Why: `make docker-run` starts only the frontend container, so nginx must
# proxy backend routes instead of serving `index.html` for API requests.
# How: override FRONTEND_*_UPSTREAM with reachable backend base URLs when the
# defaults do not match your environment.
# Example:
#   FRONTEND_AGENTIC_UPSTREAM=http://host.docker.internal:8000 \
#   FRONTEND_KNOWLEDGE_FLOW_UPSTREAM=http://host.docker.internal:8111 \
#   FRONTEND_CONTROL_PLANE_UPSTREAM=http://host.docker.internal:8222 \
#   /usr/local/bin/fred-frontend-entrypoint.sh
# FRONTEND_DNS_RESOLVER overrides the resolver nginx uses for optional
# upstreams (default: the container's own nameserver, from /etc/resolv.conf,
# falling back to Docker's embedded DNS 127.0.0.11).
# Hosted application routes use the same Control Plane upstream and SQL registry.
# FRONTEND_THEME_URL installs a branding archive over images/, contrib/,
# theme-custom.css, theme-properties.json, theme-translations/ and root markdown at startup.
# FRONTEND_THEME_S3_* and FRONTEND_THEME_REQUIRED
# tune it. Layout and variables: apps/frontend/README.md, "Theme overlay".
: "${FRONTEND_AGENTIC_UPSTREAM:=http://fred-agents}"
: "${FRONTEND_KNOWLEDGE_FLOW_UPSTREAM:=http://knowledge-flow-backend:8000}"
: "${FRONTEND_MONITOR_UPSTREAM:=http://monitor:8223}"
: "${FRONTEND_CONTROL_PLANE_UPSTREAM:=http://control-plane-backend:8222}"
: "${FRONTEND_CLIENT_MAX_BODY_SIZE:=150m}"
: "${FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE:=10m}"
: "${FRONTEND_NGINX_CONFIG:=/etc/nginx/conf.d/fred.conf}"
FRONTEND_THEME_DIR=/var/lib/fred/theme
# Overridable only so the proxy smoke test can skip it outside the image.
: "${FRONTEND_THEME_OVERLAY_SCRIPT:=/usr/local/bin/fred-theme-overlay.sh}"
# Refuse the retired authority rather than silently ignoring operator intent.
if [ "${FRONTEND_APPLICATIONS_JSON+x}" = x ] || [ "${FRONTEND_ENABLE_APPLICATIONS+x}" = x ]; then
    echo "Applications are managed in Control Plane SQL via Admin > Applications; remove FRONTEND_APPLICATIONS_JSON and FRONTEND_ENABLE_APPLICATIONS" >&2
    exit 1
fi
if ! printf '%s' "${FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE}" | grep -Eq '^[1-9][0-9]*[kKmMgG]?$'; then
    echo "FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE must be a positive nginx size" >&2
    exit 1
fi

sh "${FRONTEND_THEME_OVERLAY_SCRIPT}" "${FRONTEND_THEME_DIR}"
# nginx has no use for the store credential.
unset FRONTEND_THEME_S3_ACCESS_KEY FRONTEND_THEME_S3_SECRET_KEY

# Resolve optional backends at request time so an absent service cannot stop nginx.
if [ -z "${FRONTEND_DNS_RESOLVER:-}" ]; then
    FRONTEND_DNS_RESOLVER="$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf 2>/dev/null || true)"
fi
: "${FRONTEND_DNS_RESOLVER:=127.0.0.11}"

{
# Only bounded route families enter access logs: no raw paths, queries or headers.
cat <<'EOF'
map $status $fred_log_severity {
    default INFO;
    ~^4 WARNING;
    ~^5 ERROR;
}
map $request_uri $fred_log_route {
    default frontend;
    ~^/fred/agents/v2(?:/|[?]|$) agent;
    ~^/knowledge-flow(?:/|[?]|$) knowledge-flow;
    ~^/monitor(?:/|[?]|$) monitor;
    ~^/control-plane(?:/|[?]|$) control-plane;
    ~^/apps(?:/|[?]|$) application-ui;
    ~^/app-services(?:/|[?]|$) application-service;
}
log_format fred_json escape=json
    '{"timestamp":"$time_iso8601","severity":"$fred_log_severity",'
    '"message":"HTTP request completed","logger":"nginx.access",'
    '"service":"frontend","service_role":"proxy","category":"access",'
    '"request_id":"$request_id","http_method":"$request_method",'
    '"http_route":"$fred_log_route","http_status":$status,'
    '"duration_s":$request_time,"response_bytes":$body_bytes_sent}';
EOF

cat <<EOF
server {
    listen 8080;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html index.htm;
    access_log /dev/stdout fred_json;
    error_log /dev/stderr warn;
    client_max_body_size ${FRONTEND_CLIENT_MAX_BODY_SIZE};
    resolver ${FRONTEND_DNS_RESOLVER} valid=10s;

    location /fred/agents/v2 {
        set \$fred_agentic_upstream ${FRONTEND_AGENTIC_UPSTREAM};
        proxy_pass \$fred_agentic_upstream;
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
        set \$fred_knowledge_flow_upstream ${FRONTEND_KNOWLEDGE_FLOW_UPSTREAM};
        proxy_pass \$fred_knowledge_flow_upstream;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /monitor/ {
        set \$fred_monitor_upstream ${FRONTEND_MONITOR_UPSTREAM};
        proxy_pass \$fred_monitor_upstream;
        proxy_http_version 1.1;
        proxy_read_timeout 15;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /control-plane/ {
        set \$fred_control_plane_upstream ${FRONTEND_CONTROL_PLANE_UPSTREAM};
        proxy_pass \$fred_control_plane_upstream;
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }


EOF

# Fixed routes: Control Plane owns registration, authorization and upstream paths.
for prefix in apps app-services; do
cat <<EOF
    location = /${prefix} {
        return 404;
    }

    location ^~ /${prefix}/ {
        set \$fred_control_plane_upstream ${FRONTEND_CONTROL_PLANE_UPSTREAM};
        proxy_pass \$fred_control_plane_upstream;
        client_max_body_size ${FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }
EOF
done

cat <<'EOF'
    # Deployment theme: the overlay directory is tried first for these surfaces
    # only, so index.html, config.json and the bundle are never overridable,
    # and a missing asset is a real 404 rather than the SPA shell.
    location ~ "^/(images|contrib)/|^/[^/]+\.md$" {
EOF
printf '        root %s;\n' "${FRONTEND_THEME_DIR}"
cat <<'EOF'
        try_files $uri @stock;
    }

    location @stock {
        try_files $uri =404;
    }

    # try_files drops the calling location's headers on the internal redirect.
    location @stock_nocache {
        add_header Cache-Control "no-cache";
        try_files $uri =404;
    }

    location = /theme-properties.json {
        add_header Cache-Control "no-cache";
EOF
printf '        root %s;\n' "${FRONTEND_THEME_DIR}"
cat <<'EOF'
        try_files $uri @stock_nocache;
    }

    location = /theme-catalog.json {
        add_header Cache-Control "no-cache";
EOF
printf '        root %s;\n' "${FRONTEND_THEME_DIR}"
cat <<'EOF'
        try_files $uri @stock_nocache;
    }

    location = /theme-custom.css {
        add_header Cache-Control "no-cache";
EOF
printf '        root %s;\n' "${FRONTEND_THEME_DIR}"
cat <<'EOF'
        try_files $uri @stock_nocache;
    }

    location ~ "^/theme-translations/(en|fr)\.json$" {
        add_header Cache-Control "no-cache";
EOF
printf '        root %s;\n' "${FRONTEND_THEME_DIR}"
cat <<'EOF'
        try_files $uri @stock_nocache;
    }

    # Applies the stored UI theme before the first paint; must never be stale,
    # or a removed theme id would leave the page without theme tokens.
    location = /theme-boot.js {
        add_header Cache-Control "no-cache";
        try_files $uri =404;
    }

    # Hashed bundles never change, so cache them for good; a missing one must
    # 404, not fall back to index.html, which the browser rejects as a module.
    location ^~ /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;

        # ^~ skips the \.mjs$ location below, and the pdf.js worker lives here.
        location ~ \.mjs$ {
            try_files $uri =404;
            default_type application/javascript;
            types {
                application/javascript                       mjs;
            }
        }
    }

    # index.html names the current chunks; a cached copy points at a past deploy.
    location / {
        add_header Cache-Control "no-cache";
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
