#!/usr/bin/env bash

CLUSTER_HOSTNAME="{{ .Values.scripts.cluster.hostname }}"
CLUSTER_PORT="{{ .Values.scripts.cluster.port }}"
INDICE_NAME="{{ .Values.scripts.createIndice.indice.name }}"
USER_NAME="{{ .Values.scripts.createIndice.user.name }}"
USER_PASSWORD="{{ .Values.scripts.createIndice.user.password }}"
CURL_CMD="curl --fail --insecure --silent --user ${USER_NAME}:${USER_PASSWORD}"

cd $(dirname $0)

# Check if indice is defined
if [ -z "$INDICE_NAME" ]
then
    echo "Indice is not defined ... Job aborted"
    exit 0
fi

# Check if opensearch cluster is reachable
if ! $CURL_CMD https://${CLUSTER_HOSTNAME}:${CLUSTER_PORT}
then
    echo "Cannot connect to ${CLUSTER_HOSTNAME}:${CLUSTER_PORT}" >&2
    exit 1
fi

# Check if indice already exists
if $CURL_CMD https://${CLUSTER_HOSTNAME}:${CLUSTER_PORT}/${INDICE_NAME}
then
    echo "Indice already exists"
    exit 0
fi

{{- if .Values.scripts.createIndice.indice.definition }}
# Prepare definition file for the indice
cat << EOF > /tmp/indice_definition.json
{{ .Values.scripts.createIndice.indice.definition -}}
EOF
{{- end }}

# Create the indice
$CURL_CMD https://${CLUSTER_HOSTNAME}:${CLUSTER_PORT}/${INDICE_NAME} \
{{- if .Values.scripts.createIndice.indice.definition }}
    --data-binary @/tmp/indice_definition.json \
    --header "Content-Type: application/json" \
{{- end }}
    --request PUT