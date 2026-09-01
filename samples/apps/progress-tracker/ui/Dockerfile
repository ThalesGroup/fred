# Serving the bare prefix directly and disabling absolute_redirect are both
# load-bearing, not style: the iframe src has no trailing slash, and Fred
# forwards Location verbatim. Full rationale: README.md.
FROM nginx:1.27-alpine

RUN mkdir -p /usr/share/nginx/html/apps/progress-tracker
COPY index.html /usr/share/nginx/html/apps/progress-tracker/index.html

RUN printf '%s\n' \
  'server {' \
  '  listen 80;' \
  '  root /usr/share/nginx/html;' \
  '  absolute_redirect off;' \
  '  location = /apps/progress-tracker { add_header Cache-Control "no-store"; try_files /apps/progress-tracker/index.html =404; }' \
  '  location /apps/progress-tracker/ {' \
  '    add_header Cache-Control "no-store";' \
  '    try_files $uri $uri/ /apps/progress-tracker/index.html;' \
  '  }' \
  '  location = /healthz { return 200 "ok"; add_header content-type text/plain; }' \
  '}' > /etc/nginx/conf.d/default.conf
