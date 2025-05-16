#!/usr/bin/env bash

while ! /usr/share/opensearch/plugins/opensearch-security/tools/securityadmin.sh \
    --accept-red-cluster \
    --configdir /usr/share/opensearch/config/opensearch-security/ \
    --ignore-clustername \
    --disable-host-name-verification \
    --hostname fred-opensearch \
    --port 9200 \
    -cacert /usr/share/opensearch/config/certs/ca.crt \
    -cert /usr/share/opensearch/config/certs/admin.crt \
    -key /usr/share/opensearch/config/certs/admin.key
do
    sleep 5
done
