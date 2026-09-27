{{/*
Resolve one application entry against the one it inherits from.

An application may declare `inheritFrom: <other application>`; its own keys are
then deep-merged over that application's. Unlike a YAML anchor in values.yaml,
which is resolved when that one file is parsed, this runs after Helm has merged
every -f and --set, so overriding the base application also reaches the ones
inheriting from it.

Returns the resolved application as YAML; callers pipe it through `fromYaml`.
*/}}
{{- define "fred.resolvedApp" -}}
{{- $app := .app -}}
{{- $base := index .root.Values.applications .app.inheritFrom -}}
{{- if not $base -}}
{{- fail (printf "applications.%s.inheritFrom: no application named %q" .name .app.inheritFrom) -}}
{{- end -}}
{{- if hasKey $base "inheritFrom" -}}
{{- fail (printf "applications.%s.inheritFrom: %q inherits too, which is not supported" .name .app.inheritFrom) -}}
{{- end -}}
{{- mergeOverwrite (deepCopy $base) (deepCopy $app) | toYaml -}}
{{- end -}}
