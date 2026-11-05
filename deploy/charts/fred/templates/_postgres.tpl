{{- define "fred.postgres-env" -}}
{{- $secrets := .root.Values.postgresSecrets -}}
{{- $key := "" -}}
{{- $variable := "FRED_POSTGRES_PASSWORD" -}}
{{- if hasPrefix "control-plane" .name -}}
  {{- $key = $secrets.controlPlaneKey -}}
{{- else if hasPrefix "knowledge-flow" .name -}}
  {{- $key = $secrets.knowledgeKey -}}
{{- else if or (eq .name "fred-agents") (eq .name "fred-agents-worker") -}}
  {{- $key = $secrets.runtimeKey -}}
{{- else if eq .name "monitor" -}}
  {{- $key = $secrets.monitorUrlKey -}}
  {{- $variable = "DATABASE_URL" -}}
{{- end -}}
{{- $provided := false -}}
{{- range concat (.app.env | default list) (.app.extraEnvVars | default list) -}}
  {{- if eq .name $variable -}}{{- $provided = true -}}{{- end -}}
{{- end -}}
{{- if and $key (not $provided) -}}
- name: {{ $variable }}
  valueFrom:
    secretKeyRef: {name: {{ $secrets.name | quote }}, key: {{ $key | quote }}}
{{- end -}}
{{- end -}}
