#!/usr/bin/env bash

COUNTRY="{{ .Values.caCert.country }}"
STATE="{{ .Values.caCert.state }}"
LOCATION="{{ .Values.caCert.location }}"
ORGANIZATION="{{ .Values.caCert.organization }}"

generate_cert() {
    local NAME=$1
    local COMMON_NAME=$2
    openssl genpkey -algorithm RSA -out ${NAME}.key -pkeyopt rsa_keygen_bits:4096
    openssl req -new -key ${NAME}.key -out ${NAME}.csr -subj "/C=${COUNTRY}/ST=${STATE}/L=${LOCATION}/O=${ORGANIZATION}/CN=${COMMON_NAME}"
    openssl x509 -req -in ${NAME}.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out ${NAME}.crt -days 365 -sha256
    cat ${NAME}.crt ${NAME}.key > ${NAME}.pem
}

openssl genpkey -algorithm RSA -out ca.key -pkeyopt rsa_keygen_bits:4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt -subj "/C=${COUNTRY}/ST=${STATE}/L=${LOCATION}/O=${ORGANIZATION}/CN=OpenSearch CA"

generate_cert "transport" "node"
generate_cert "admin" "admin"
generate_cert "rest" "rest"

kubectl create secret generic opensearch-certificates \
    --from-file=ca.crt \
    --from-file=ca.key \
    --from-file=transport.crt \
    --from-file=transport.key \
    --from-file=transport.pem \
    --from-file=admin.crt \
    --from-file=admin.key \
    --from-file=admin.pem \
    --from-file=rest.crt \
    --from-file=rest.key \
    --from-file=rest.pem \
    --dry-run=client -o yaml | kubectl apply -f -