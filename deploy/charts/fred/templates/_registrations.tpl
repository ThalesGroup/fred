{{/*
What `registrations` registers, for its two consumers: the control plane's
application_sources and publishers, and the frontend gateway's entries. Each
application's key is its app_id, and feeds both halves.

Returns YAML; callers pipe it through `fromYaml`. Maps range in key order.
*/}}
{{- define "fred.registrations" -}}
{{- $registrations := .Values.registrations | default dict -}}
{{- $sources := list -}}
{{- $gateways := list -}}
{{- $publishers := list -}}
{{- range $appId, $entry := $registrations.applications | default dict -}}
{{- if $entry -}}
{{- $sources = append $sources (merge (dict "app_id" $appId) (omit $entry "gateway")) -}}
{{- $gateways = append $gateways (merge (dict "app_id" $appId) $entry.gateway) -}}
{{- end -}}
{{- end -}}
{{- range $clientId, $entry := $registrations.knowledgeBasePublishers | default dict -}}
{{- if $entry -}}
{{- $publishers = append $publishers (merge (dict "client_id" $clientId) $entry) -}}
{{- end -}}
{{- end -}}
{{- dict "application_sources" $sources "gateways" $gateways "publishers" $publishers | toYaml -}}
{{- end -}}

{{/*
Refuse the former registration values: setting them would silently compete
with `registrations`.
*/}}
{{- define "fred.validate-registrations" -}}
{{- $controlPlane := index .Values.applications "control-plane-backend" | default dict -}}
{{- if hasKey (dig "configuration" "platform" dict $controlPlane) "application_sources" -}}
{{- fail "applications.control-plane-backend.configuration.platform.application_sources is derived from registrations.applications: register each application there, keyed by its app_id" -}}
{{- end -}}
{{- if hasKey (dig "configuration" "knowledge_bases" dict $controlPlane) "publishers" -}}
{{- fail "applications.control-plane-backend.configuration.knowledge_bases.publishers is derived from registrations.knowledgeBasePublishers: register each publisher there, keyed by its client_id" -}}
{{- end -}}
{{- $frontend := .Values.applications.frontend | default dict -}}
{{- range concat ($frontend.env | default list) ($frontend.extraEnvVars | default list) -}}
{{- if eq (.name | toString) "FRONTEND_APPLICATIONS_JSON" -}}
{{- fail "applications.frontend FRONTEND_APPLICATIONS_JSON is derived from registrations.applications: give each application's upstreams as registrations.applications.<app_id>.gateway" -}}
{{- end -}}
{{- end -}}
{{- end -}}
