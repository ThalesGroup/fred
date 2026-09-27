{{/*
Refuse to render when the enabled knowledge-flow worker deployments do not cover
the four ingestion worker roles between them.

Extraction is routed to a queue derived from the document's profile, and an
activity sitting on a queue nobody polls is never rescheduled and never times
out: its start_to_close_timeout only starts counting once a worker picks it up.
The document stays "processing" forever with nothing in any log. A deployment
that routes to a queue it does not serve therefore has to fail here, at install,
rather than at the first rich upload.

A worker is recognised by the entrypoint it runs, not by its name, so renaming a
deployment cannot quietly take it out of this check. One process may serve
several roles (the single-pod local cluster serves all four), so what matters is
the union across the enabled deployments, not one role each.
*/}}
{{- define "fred.validate-ingestion-worker-roles" -}}
{{- $allRoles := list "common" "extraction-fast" "extraction-medium" "extraction-rich" -}}
{{- $served := list -}}
{{- $workers := list -}}
{{- range $name, $rawApp := .Values.applications -}}
  {{- $app := $rawApp -}}
  {{- if hasKey $rawApp "inheritFrom" -}}
    {{- $app = include "fred.resolvedApp" (dict "app" $rawApp "root" $ "name" $name) | fromYaml -}}
  {{- end -}}
  {{- $command := (($app.command) | default dict) -}}
  {{- $isWorker := and $command.enabled (has "knowledge_flow_backend.main_worker" ($command.data | default list)) -}}
  {{- $running := and (dig "enabled" false $app) (dig "deployment" "enabled" false $app) -}}
  {{- $scheduler := (($app.configuration) | default dict).scheduler | default dict -}}
  {{- if and $isWorker $running $scheduler.enabled (eq ($scheduler.backend | default "temporal") "temporal") -}}
    {{- $workers = append $workers $name -}}
    {{- $served = concat $served ($scheduler.worker_roles | default $allRoles) -}}
  {{- end -}}
{{- end -}}
{{- if $workers -}}
  {{- $missing := list -}}
  {{- range $role := $allRoles -}}
    {{- if not (has $role $served) -}}
      {{- $missing = append $missing $role -}}
    {{- end -}}
  {{- end -}}
  {{- if $missing -}}
    {{- fail (printf "knowledge-flow ingestion: no enabled worker serves %s. Enabled workers: %s. Enable the matching knowledge-flow-worker-<role> deployment(s), or add the role(s) to an enabled worker's configuration.scheduler.worker_roles. Documents routed to an unserved queue wait there indefinitely." (join ", " $missing) (join ", " $workers)) -}}
  {{- end -}}
{{- end -}}
{{- end -}}
