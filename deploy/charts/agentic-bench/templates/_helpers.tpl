{{- define "agentic-bench.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "agentic-bench.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "agentic-bench.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "agentic-bench.labels" -}}
helm.sh/chart: {{ include "agentic-bench.name" . }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "agentic-bench.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "agentic-bench.mode" -}}
{{- $mode := default "rag" .Values.bench.mode -}}
{{- if or (eq $mode "normal") (eq $mode "rag") (eq $mode "existing") -}}
{{- $mode -}}
{{- else -}}
{{- fail (printf "unsupported bench.mode %q (expected \"normal\", \"rag\", or \"existing\")" $mode) -}}
{{- end -}}
{{- end -}}

{{- define "agentic-bench.modeConfig" -}}
{{- $mode := include "agentic-bench.mode" . -}}
{{- if hasKey .Values.bench.modes $mode -}}
{{- $mode -}}
{{- else -}}
{{- fail (printf "bench.modes.%s is required" $mode) -}}
{{- end -}}
{{- end -}}
