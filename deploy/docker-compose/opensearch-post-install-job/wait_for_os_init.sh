#!/usr/bin/env bash

CURL_CMD="curl https://fred-opensearch:9200/_cluster/health --insecure --silent --user admin:Azerty123_ --request GET"

cat << EOF

Waiting for OpenSearch initialization

EOF

while ! $CURL_CMD || $CURL_CMD | grep -q "OpenSearch Security not initialized"
do
    echo
    sleep 1
done

echo
