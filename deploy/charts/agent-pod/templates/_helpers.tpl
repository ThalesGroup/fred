{{- define "agent-pod.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agent-pod.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "agent-pod.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "agent-pod.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agent-pod.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "agent-pod.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "agent-pod.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: agent-pod
{{- end -}}

{{/* The chart deploys someone's image: no default. */}}
{{- define "agent-pod.image" -}}
{{- $repository := required "image.repository is required: the agent pod's image" .Values.image.repository -}}
{{- $tag := required "image.tag is required: the agent pod's image tag" .Values.image.tag -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}

{{- define "agent-pod.configMapName" -}}
{{- printf "%s-config" (include "agent-pod.fullname" .) -}}
{{- end -}}

{{- define "agent-pod.port" -}}
{{- .Values.configuration.app.port | default 8000 -}}
{{- end -}}

{{/* The pod's path, also its ingress_prefix: canonical, as the Control Plane requires. */}}
{{- define "agent-pod.basePath" -}}
{{- $path := required "configuration.app.base_url is required: the path the pod serves, and its ingress_prefix in Fred" .Values.configuration.app.base_url -}}
{{- if or (not (hasPrefix "/" $path)) (hasSuffix "/" $path) (contains "//" $path) (regexMatch "(^|/)\\.\\.?(/|$)" $path) -}}
{{- fail (printf "configuration.app.base_url must be a canonical root-relative path such as /my/agents/v2 (leading /, no trailing /, no // or . segments), got %q" $path) -}}
{{- end -}}
{{- $path -}}
{{- end -}}

{{/*
The Prometheus exporter, when the KPI configuration enables it. The library binds it
to 127.0.0.1 unless told otherwise, which no scraper reaches: refuse to expose that.
*/}}
{{- define "agent-pod.metricsPort" -}}
{{- $prometheus := dig "observability" "kpi" "prometheus" dict .Values.configuration -}}
{{- if $prometheus.enabled -}}
{{- include "agent-pod.reachableMetrics" (dict "path" "observability.kpi.prometheus" "address" $prometheus.address) -}}
{{ $prometheus.port | default 9000 }}
{{- end -}}
{{- end -}}

{{- define "agent-pod.reachableMetrics" -}}
{{- $address := .address | default "127.0.0.1" -}}
{{- if or (hasPrefix "127." $address) (eq $address "localhost") (eq $address "::1") -}}
{{- fail (printf "configuration.%s.address is %s: set 0.0.0.0, or Prometheus cannot reach the metrics port the chart opens" .path $address) -}}
{{- end -}}
{{- end -}}

{{- define "agent-pod.secretName" -}}
{{- if .Values.secret.create -}}
{{- printf "%s-secret" (include "agent-pod.fullname" .) -}}
{{- else -}}
{{- .Values.secret.existingSecret -}}
{{- end -}}
{{- end -}}

{{/*
The pod authenticates to Fred with its M2M client: the variable that
configuration.security.m2m.secret_env_var names must reach it. A whole Secret cannot
be inspected at render time; an extraEnvVars list must name that variable.
*/}}
{{- define "agent-pod.requireM2MSecret" -}}
{{- if dig "security" "m2m" "enabled" true .Values.configuration -}}
{{- $variable := dig "security" "m2m" "secret_env_var" "M2M_CLIENT_SECRET" .Values.configuration -}}
{{- if not (include "agent-pod.secretName" .) -}}
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

{{/* The container's environment: the configuration file, then the credentials. */}}
{{- define "agent-pod.env" -}}
{{- include "agent-pod.requireM2MSecret" . -}}
{{- $secretName := include "agent-pod.secretName" . -}}
env:
  - name: CONFIG_FILE
    value: /app/config/configuration.yaml
  {{- with .Values.extraEnvVars }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
{{- with $secretName }}
envFrom:
  - secretRef:
      name: {{ . }}
{{- end }}
{{- end -}}
