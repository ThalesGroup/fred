#!/usr/bin/env bash
set -Eeuo pipefail

# Fred local setup: key before Helm sync; dashboards and guidance after it.
fred_dir="$(cd "$(dirname "$0")/../.." && pwd)"
: "${KUBE_CONTEXT:?factory must provide the explicit k3d context}"
ns="${K3D_NAMESPACE:-fred}"
timeout=1200s
kubectl() { command kubectl --context "$KUBE_CONTEXT" "$@"; }
step() { printf '%s\n' "$*"; }
ok() { printf '%s\n' "$*"; }
warn() { printf 'Warning: %s\n' "$*" >&2; }
info() { printf '%s\n' "$*"; }
umask 077
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mode="${1:?usage: configure.sh key|finish}"
[[ "$mode" == key || "$mode" == finish ]] || { echo "Unknown setup phase: $mode" >&2; exit 1; }
if [[ "$mode" == key ]]; then
  env_file="$fred_dir/apps/fred-agents/config/.env"
  key="${OPENAI_API_KEY:-}"
  if [[ -z "$key" && -f "$env_file" ]]; then
    key="$(sed -n 's/^OPENAI_API_KEY=//p' "$env_file" | tail -n1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
  fi
  current="$(kubectl get secret fred-secrets -n "$ns" -o jsonpath='{.data.OPENAI_API_KEY}')"
  key_changed=false
  if [[ -z "$key" ]]; then
    [[ -n "$current" ]] || warn "No model API key (OPENAI_API_KEY in $env_file, see 'make setup-env' in fred): Fred starts, every chat fails"
  elif [[ "$(printf '%s' "$key" | base64 -w0)" != "$current" ]]; then
    patch="$tmp/key-patch.json"
    printf '{"data":{"OPENAI_API_KEY":"%s"}}' "$(printf '%s' "$key" | base64 -w0)" >"$patch"
    kubectl patch secret fred-secrets -n "$ns" --type merge --patch-file "$patch" >/dev/null
    rm -f "$patch"
    key_changed=true
    ok "Model API key written to fred-secrets"
  fi

  # Existing consumers need a restart; a fresh installation has none yet.
  if $key_changed; then
    deployments="$(kubectl get deployments -n "$ns" -l 'app in (fred-agents,knowledge-flow-backend,knowledge-flow-worker)' -o name)"
    while IFS= read -r deployment; do
      [[ -z "$deployment" ]] || kubectl rollout restart "$deployment" -n "$ns" >/dev/null
    done <<< "$deployments"
  fi
  exit 0
fi

# Fred's own Grafana dashboards, from this checkout. They are made for the
# Import page (a ${DS_PROMETHEUS} input); file provisioning resolves no input,
# so the input becomes the uid of the stack's Prometheus data source.
if kubectl get deployment grafana -n "$ns" >/dev/null 2>&1 && compgen -G "$fred_dir/deploy/grafana/*.json" >/dev/null; then
  dashboards="$tmp/dashboards"
  mkdir "$dashboards"
  for f in "$fred_dir"/deploy/grafana/*.json; do
    sed 's/\${DS_PROMETHEUS}/prometheus/g' "$f" >"$dashboards/$(basename "$f")"
  done
  # Absent on a fresh cluster: then "before" is the hash of nothing.
  before="$( { kubectl get configmap grafana-dashboards -n "$ns" -o jsonpath='{.data}' 2>/dev/null || true; } | sha256sum)"
  kubectl create configmap grafana-dashboards -n "$ns" --from-file="$dashboards" --dry-run=client -o yaml \
    | kubectl apply -f - >/dev/null
  rm -rf "$dashboards"
  # Grafana started before the ConfigMap existed never sees it (an optional
  # volume is not filled in later): restart it whenever the dashboards change.
  if [[ "$(kubectl get configmap grafana-dashboards -n "$ns" -o jsonpath='{.data}' | sha256sum)" != "$before" ]]; then
    kubectl rollout restart deployment/grafana -n "$ns" >/dev/null
    kubectl rollout status deployment/grafana -n "$ns" --timeout "$timeout" >/dev/null
  fi
  ok "Fred's Grafana dashboards loaded: http://localhost:${K3D_HOST_PORT_GRAFANA:-3002} (folder Fred)"
fi

ok "Fred is running: http://localhost:${K3D_HOST_PORT_FRONTEND:-8088}"
if ! getent hosts keycloak >/dev/null; then
  warn "'keycloak' does not resolve on this machine: the browser cannot log in. Once, with sudo:"
  printf '       grep -qw keycloak /etc/hosts || echo "127.0.0.1 keycloak" | sudo tee -a /etc/hosts\n'
fi
# Explain token retrieval only while the first-login bootstrap is needed.
if curl --max-time 10 -fsS "http://localhost:${K3D_HOST_PORT_FRONTEND:-8088}/control-plane/v1/frontend/config" 2>/dev/null \
    | grep -Eq '"root_bootstrap_required": ?true'; then
  info "First login: open Fred, create your account with Register on the login page,"
  info "Retrieve the bootstrap token locally, then paste it where Fred asks for it:"
  printf "kubectl --context %q -n %q get secret fred-secrets -o jsonpath='{.data.CONTROL_PLANE_BOOTSTRAP_TOKEN}' | base64 -d; echo\n" "$KUBE_CONTEXT" "$ns"
fi
