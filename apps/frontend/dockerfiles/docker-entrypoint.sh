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
: "${FRONTEND_AGENTIC_UPSTREAM:=http://fred-agents}"
: "${FRONTEND_KNOWLEDGE_FLOW_UPSTREAM:=http://knowledge-flow-backend:8000}"
: "${FRONTEND_CONTROL_PLANE_UPSTREAM:=http://control-plane-backend:8222}"
: "${FRONTEND_EVALUATION_UPSTREAM:=http://fred-evaluation-backend}"
: "${FRONTEND_CLIENT_MAX_BODY_SIZE:=150m}"

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

cat > /etc/nginx/conf.d/fred.conf <<EOF
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

    location / {
        try_files \$uri /index.html;
    }

    # Ensure ES module workers (.mjs) are served with a JS MIME type.
    location ~ \.mjs\$ {
        try_files \$uri =404;
        default_type application/javascript;
        types {
            application/javascript                           mjs;
        }
    }
}
EOF

exec nginx -g 'daemon off;'
