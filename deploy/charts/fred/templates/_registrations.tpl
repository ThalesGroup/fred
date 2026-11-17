{{/* Reject retired application configuration: PostgreSQL is the only registry. */}}
{{- define "fred.validate-registrations" -}}
{{- $registrations := .Values.registrations | default dict -}}
{{- $controlPlane := index .Values.applications "control-plane-backend" | default dict -}}
{{- if or ($registrations.applications | default dict) (hasKey (dig "configuration" "platform" dict $controlPlane) "application_sources") (hasKey (dig "configuration" "platform" "frontend" "feature_flags" dict $controlPlane) "enableApplications") -}}
{{- fail "Applications are managed in Control Plane SQL via Admin > Applications: remove registrations.applications, platform.application_sources and enableApplications" -}}
{{- end -}}
{{- if or ($registrations.knowledgeBasePublishers | default dict) (hasKey (dig "configuration" "knowledge_bases" dict $controlPlane) "publishers") -}}
{{- fail "knowledgeBasePublishers and knowledge_bases.publishers are not supported by Weaver" -}}
{{- end -}}
{{- $frontend := .Values.applications.frontend | default dict -}}
{{- range concat ($frontend.env | default list) ($frontend.extraEnvVars | default list) -}}
{{- if has (.name | toString) (list "FRONTEND_APPLICATIONS_JSON" "FRONTEND_ENABLE_APPLICATIONS") -}}
{{- fail "Applications are managed in Control Plane SQL via Admin > Applications: remove FRONTEND_APPLICATIONS_JSON and FRONTEND_ENABLE_APPLICATIONS" -}}
{{- end -}}
{{- end -}}
{{- end -}}
