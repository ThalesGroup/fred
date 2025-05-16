#!/usr/bin/env bash

cd $(dirname $0)

cat << EOF

Create first indice

EOF

if ! curl -v https://fred-opensearch:9200/localvector \
    --fail \
    --insecure \
    --silent \
    --user admin:Azerty123_
then
    curl -v https://fred-opensearch:9200/localvector \
        --insecure \
        --silent \
        --user admin:Azerty123_ \
        --request PUT \
        --data-binary @mapping.json \
        --header "Content-Type: application/json"
fi