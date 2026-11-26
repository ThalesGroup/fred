{{/* A digest pins the exact build; tagged releases retain appVersion fallback. */}}
{{- define "fred.image" -}}
{{- if .image.digest -}}
{{- printf "%s@%s" .image.repository .image.digest -}}
{{- else -}}
{{- printf "%s:%s" .image.repository (.image.tag | default .root.Chart.AppVersion) -}}
{{- end -}}
{{- end -}}
