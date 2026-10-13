{{- define "knowledge-base.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "knowledge-base.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "knowledge-base.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "knowledge-base.selectorLabels" -}}
app.kubernetes.io/name: {{ include "knowledge-base.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "knowledge-base.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "knowledge-base.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: knowledge-base
{{- end -}}

{{/* The chart deploys someone's image: no default. */}}
{{- define "knowledge-base.image" -}}
{{- $repository := required "image.repository is required: the Knowledge Base pod's image" .Values.image.repository -}}
{{- $tag := required "image.tag is required: the Knowledge Base pod's image tag" .Values.image.tag -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}

{{- define "knowledge-base.configMapName" -}}
{{- printf "%s-config" (include "knowledge-base.fullname" .) -}}
{{- end -}}

{{- define "knowledge-base.secretName" -}}
{{- if .Values.secret.create -}}
{{- printf "%s-secret" (include "knowledge-base.fullname" .) -}}
{{- else -}}
{{- .Values.secret.existingSecret -}}
{{- end -}}
{{- end -}}

{{/*
The metrics endpoints the worker serves, as name/port pairs, from the same
configuration the pod reads. Empty when both are disabled.
*/}}
{{- define "knowledge-base.metricsPorts" -}}
{{- $kpi := dig "observability" "kpi" "prometheus" dict .Values.configuration -}}
{{- $temporal := dig "observability" "temporal" "prometheus" dict .Values.configuration -}}
{{- if $kpi.enabled }}
{{- include "knowledge-base.reachableMetrics" (dict "path" "observability.kpi.prometheus" "address" $kpi.address) }}
- name: metrics
  port: {{ $kpi.port | default 9000 }}
{{- end }}
{{- if $temporal.enabled }}
{{- include "knowledge-base.reachableMetrics" (dict "path" "observability.temporal.prometheus" "address" $temporal.address) }}
- name: engine-metrics
  port: {{ $temporal.port | default 9001 }}
{{- end }}
{{- end -}}

{{/* The libraries bind metrics to 127.0.0.1 unless told otherwise: refuse to expose that. */}}
{{- define "knowledge-base.reachableMetrics" -}}
{{- $address := .address | default "127.0.0.1" -}}
{{- if or (hasPrefix "127." $address) (eq $address "localhost") (eq $address "::1") -}}
{{- fail (printf "configuration.%s.address is %s: set 0.0.0.0, or Prometheus cannot reach the metrics port the chart opens" .path $address) -}}
{{- end -}}
{{- end -}}

{{/*
One container, for the `run` worker and the `publish` Job alike: the image, its
command, the configuration file and the credentials. The M2M secret must reach it
(knowledge-base.requireM2MSecret).
Called with (dict "root" $ "command" "run|publish" "resources" ...).
*/}}
{{- define "knowledge-base.container" -}}
{{- $root := .root -}}
{{- include "knowledge-base.requireM2MSecret" $root -}}
{{- $secretName := include "knowledge-base.secretName" $root -}}
- name: {{ .command }}
  image: {{ include "knowledge-base.image" $root | quote }}
  imagePullPolicy: {{ $root.Values.image.pullPolicy }}
  args:
    - {{ .command }}
  {{- with .ports }}
  ports:
    {{- range . }}
    - name: {{ .name }}
      containerPort: {{ .port }}
      protocol: TCP
    {{- end }}
  {{- end }}
  securityContext:
    {{- toYaml $root.Values.securityContext | nindent 4 }}
  env:
    - name: CONFIG_FILE
      value: /app/config/configuration.yaml
    {{- with $root.Values.extraEnvVars }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
  {{- with $secretName }}
  envFrom:
    - secretRef:
        name: {{ . }}
  {{- end }}
  resources:
    {{- toYaml .resources | nindent 4 }}
  volumeMounts:
    - name: configuration
      mountPath: /app/config/configuration.yaml
      subPath: configuration.yaml
      readOnly: true
    - name: tmp
      mountPath: /tmp
    {{- with $root.Values.extraVolumeMounts }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
{{- end -}}

{{/* What the worker and the Job's pods share besides their container. */}}
{{- define "knowledge-base.podSpec" -}}
automountServiceAccountToken: false
enableServiceLinks: false
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
securityContext:
  {{- toYaml .Values.podSecurityContext | nindent 2 }}
volumes:
  - name: configuration
    configMap:
      name: {{ include "knowledge-base.configMapName" . }}
  - name: tmp
    emptyDir: {}
  {{- with .Values.extraVolumes }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/*
The pod authenticates to Fred with its M2M client: the variable that
configuration.security.m2m.secret_env_var names must reach it. A whole Secret cannot
be inspected at render time; an extraEnvVars list must name that variable.
*/}}
{{- define "knowledge-base.requireM2MSecret" -}}
{{- if dig "security" "m2m" "enabled" true .Values.configuration -}}
{{- $variable := dig "security" "m2m" "secret_env_var" "M2M_CLIENT_SECRET" .Values.configuration -}}
{{- if not (include "knowledge-base.secretName" .) -}}
{{- $named := false -}}
{{- range .Values.extraEnvVars -}}
{{- if eq .name $variable -}}{{- $named = true -}}{{- end -}}
{{- end -}}
{{- if not $named -}}
{{- fail (printf "credentials are required: set secret.existingSecret or secret.create, or an extraEnvVars entry named %s (configuration.security.m2m.secret_env_var)" $variable) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
