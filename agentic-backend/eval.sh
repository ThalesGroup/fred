#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# eval.sh — Évaluation DeepEval d'un agent V2 (in-process, sans serveur HTTP)
#
# USAGE
#   ./eval.sh                                          # mode interactif
#   ./eval.sh -a "SQL Agent" -d /chemin/dataset.json   # mode direct
#   ./eval.sh --agent "Corpus Investigator Deep" --dataset /chemin/dataset.json
#   ./eval.sh --help
#
# AGENTS DISPONIBLES (id à passer à --agent)
#   "SQL Agent"                  — analyse de données tabulaires via SQL
#   "Corpus Investigator Deep"   — RAG avancé sur corpus documentaire
#   "DVARiskValidatorGraph"      — validation de risques DVA
#   "DVARiskValidatorQA"         — QA sur risques DVA
#   "BankTransfer"               — agent de virement bancaire (sample)
#
# FORMAT DU DATASET (fichier JSON)
#   [
#     { "question": "Combien de ports ?",  "expect": "8" },
#     { "question": "Liste les radars." }   ← expect optionnel
#   ]
#   "expect" = sous-chaîne attendue dans la réponse (substring check + hint juge)
#
# PRÉREQUIS
#   - Être dans le dossier agentic-backend/
#   - Knowledge Flow server actif (http://localhost:8111) si l'agent en a besoin
#   - config/.env avec KEYCLOAK_AGENTIC_CLIENT_SECRET (pour le token)
#   - OPENAI_API_KEY ou judge_model Mistral configuré dans eval_config.yaml
#
# OUTPUT
#   Rapport texte complet → agentic_backend/tests/agents/output/eval_<agent>_<ts>.txt
#   Contient : chaque question, réponse, substring check, scores par métrique, résumé
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/config/.env"
EVAL_SCRIPT="$SCRIPT_DIR/agentic_backend/tests/agents/generic_v2_evaluation.py"
EVAL_CONFIG="$SCRIPT_DIR/agentic_backend/tests/agents/eval_config.yaml"
PYTHON="$SCRIPT_DIR/.venv/bin/python"
OUTPUT_DIR="$HOME/output"

# ── Couleurs ─────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[eval]${NC} $*"; }
warn()  { echo -e "${YELLOW}[eval]${NC} $*"; }
error() { echo -e "${RED}[eval]${NC} $*" >&2; exit 1; }

# ── Parse arguments CLI ───────────────────────────────────────────────────────
AGENT_ID=""
DATASET_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--agent)   AGENT_ID="$2";    shift 2 ;;
        -d|--dataset) DATASET_PATH="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) error "Argument inconnu : $1. Utilise --help." ;;
    esac
done

# ── Mode interactif si arguments manquants ────────────────────────────────────
if [[ -z "$AGENT_ID" ]]; then
    echo -n "Nom de l'agent : "
    read -r AGENT_ID
fi

if [[ -z "$DATASET_PATH" ]]; then
    echo -n "Chemin du fichier JSON de questions : "
    read -r DATASET_PATH
fi

[[ -z "$DATASET_PATH" ]] && error "Le chemin du dataset est requis."
[[ -f "$DATASET_PATH" ]] || error "Fichier introuvable : $DATASET_PATH"

# ── Chargement de .env ────────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    set -a && . "$ENV_FILE" && set +a
    info "Variables chargées depuis config/.env"
else
    warn "Pas de config/.env trouvé, on continue sans."
fi

# ── Obtention du token Keycloak ───────────────────────────────────────────────
if [[ -z "${AGENTIC_TOKEN:-}" ]]; then
    if [[ -n "${KEYCLOAK_AGENTIC_CLIENT_SECRET:-}" ]]; then
        info "Récupération du token Keycloak..."
        AGENTIC_TOKEN=$(curl -sf \
            "http://localhost:8080/realms/app/protocol/openid-connect/token" \
            --data-urlencode "client_id=agentic" \
            --data-urlencode "client_secret=$KEYCLOAK_AGENTIC_CLIENT_SECRET" \
            --data-urlencode "grant_type=client_credentials" \
            | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null) || true

        if [[ -n "$AGENTIC_TOKEN" ]]; then
            info "Token obtenu (${AGENTIC_TOKEN:0:20}...)"
        else
            warn "Keycloak injoignable — on continue sans token (OK si auth désactivée)."
            AGENTIC_TOKEN=""
        fi
    else
        warn "Pas de KEYCLOAK_AGENTIC_CLIENT_SECRET — on continue sans token."
        AGENTIC_TOKEN=""
    fi
else
    info "Token AGENTIC_TOKEN déjà présent."
fi

# ── Vérification du KF server ─────────────────────────────────────────────────
if ! curl -sf "http://localhost:8111/knowledge-flow/v1/openapi.json" -o /dev/null 2>/dev/null; then
    warn "Knowledge Flow server non détecté sur localhost:8111 — l'évaluation peut échouer."
fi

# ── Préparation du dossier de sortie ─────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
AGENT_SLUG=$(echo "$AGENT_ID" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')
LOG_FILE="$OUTPUT_DIR/eval_${AGENT_SLUG}_${TIMESTAMP}.log"

# ── Lancement ─────────────────────────────────────────────────────────────────
echo ""
info "Agent    : $AGENT_ID"
info "Dataset  : $DATASET_PATH"
info "Log      : $LOG_FILE"
echo ""

AGENTIC_TOKEN="$AGENTIC_TOKEN" \
"$PYTHON" "$EVAL_SCRIPT" \
    --config "$EVAL_CONFIG" \
    --agent_id "$AGENT_ID" \
    --dataset "$DATASET_PATH" \
    2>&1 | tee "$LOG_FILE"

info "Résultats sauvegardés dans : $LOG_FILE"
