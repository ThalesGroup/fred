#!/usr/bin/env bash

while ! {{ .Values.scripts.updateSecurityConfig.bin }} \
    --accept-red-cluster \
    --configdir  {{ .Values.scripts.updateSecurityConfig.configDir }} \
    --ignore-clustername \
    --disable-host-name-verification \
    --hostname {{ .Values.scripts.cluster.hostname }} \
    --port {{ .Values.scripts.cluster.port }} \
    -cacert {{ .Values.scripts.updateSecurityConfig.certs.cacert }} \
    -cert {{ .Values.scripts.updateSecurityConfig.certs.adminCert }} \
    -key {{ .Values.scripts.updateSecurityConfig.certs.adminKey }}
do
    sleep 5
done