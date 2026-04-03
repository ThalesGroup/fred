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
#   /usr/local/bin/fred-frontend-entrypoint.sh
: "${FRONTEND_AGENTIC_UPSTREAM:=http://agentic-backend}"
: "${FRONTEND_KNOWLEDGE_FLOW_UPSTREAM:=http://knowledge-flow-backend:8000}"
: "${FRONTEND_CONTROL_PLANE_UPSTREAM:=http://control-plane-backend:8222}"

cat > /etc/nginx/conf.d/fred.conf <<EOF
server {
    listen 8080;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html index.htm;

    location /agentic/ {
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
