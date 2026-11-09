# Architecture dossier: regenerate its generated blocks and check it against the code.
# Postgres, tbls and mermaid-cli run in throwaway containers; nothing is installed.

PYTHON          ?= python3
POSTGRES_IMAGE  ?= pgvector/pgvector:pg15
TBLS_IMAGE      ?= ghcr.io/k1low/tbls:v1.96.0
MERMAID_IMAGE   ?= minlag/mermaid-cli:11.17.0
ROOT            := $(realpath ../..)

# One entity-relationship diagram per component, from its migrations.
ER_COMPONENTS   ?= control-plane
ER_MODE         ?= write
MODEL_REFERENCE := docs/architecture/A13-models.md
MODEL_CONTRACTS := $(MODEL_REFERENCE) docs/architecture/A12-control-plane-api.md docs/architecture/A2-manager-contracts.md
MODEL_PAGES     := docs/architecture/06-resources.md docs/architecture/01-system-overview.md docs/architecture/02.3-agent-administration.md docs/architecture/08-operations.md $(MODEL_REFERENCE)
RENDER_PAGES    ?= $(wildcard *.md)

.DEFAULT_GOAL := help

##@ Architecture dossier

.PHONY: er
er: ## Regenerate generated/<component>.er.mmd from each component's migrations
	@set -e; for c in $(ER_COMPONENTS); do \
		pg=docs-er-$$c-$$$$; \
		tmp=$$(mktemp); \
		trap 'docker rm -f $$pg >/dev/null 2>&1 || true; rm -f "$$tmp"' EXIT; \
		docker run -d --name $$pg -e POSTGRES_PASSWORD=docs -p 127.0.0.1::5432 $(POSTGRES_IMAGE) >/dev/null; \
		attempt=0; until docker exec $$pg psql -U postgres -h 127.0.0.1 -c 'select 1' >/dev/null 2>&1; do \
			attempt=$$((attempt + 1)); test $$attempt -lt 60 || { echo "Postgres did not start" >&2; exit 1; }; sleep 1; \
		done; \
		docker exec -i $$pg psql -U postgres -q -v ON_ERROR_STOP=1 -v database=postgres < $(ROOT)/deploy/postgres/bootstrap.sql; \
		for migration in $(ROOT)/apps/$$c/migrations/*.sql; do \
			docker exec -i -e PGOPTIONS="-c search_path=control_plane -c role=fred_cp" $$pg psql -U postgres -q -1 -v ON_ERROR_STOP=1 < "$$migration"; \
		done; \
		docker exec -i $$pg psql -X -U postgres -qAt -v ON_ERROR_STOP=1 < tools/triggers.sql > "$$tmp"; \
		$(PYTHON) tools/docs.py tidy-triggers "$$tmp"; \
		if [ "$(ER_MODE)" = check ]; then \
			cmp "$$tmp" generated/$$c.triggers.json || { echo "Stale trigger catalogue: run make er" >&2; exit 1; }; \
		else cp "$$tmp" generated/$$c.triggers.json; fi; \
		addr=$$(docker port $$pg 5432/tcp | head -n1); \
		docker run --rm --network host $(TBLS_IMAGE) out -t mermaid \
			"postgres://postgres:docs@$$addr/postgres?sslmode=disable" > "$$tmp"; \
		$(PYTHON) tools/docs.py tidy-er "$$tmp"; \
		if [ "$(ER_MODE)" = check ]; then \
			cmp "$$tmp" generated/$$c.er.mmd || { echo "Stale SQL diagram: run make er" >&2; exit 1; }; \
		else cp "$$tmp" generated/$$c.er.mmd; fi; \
		docker rm -f $$pg >/dev/null; rm -f "$$tmp"; echo "generated/$$c.er.mmd ($(ER_MODE))"; \
	done

.PHONY: check-er
check-er: ## Compare migrations with the committed SQL diagram without rewriting it
	$(MAKE) --no-print-directory er ER_MODE=check

.PHONY: openapi
openapi: ## Regenerate apps/control-plane/openapi.json (unversioned) from the control-plane router
	$(MAKE) --no-print-directory -C $(ROOT)/apps/control-plane generate-openapi

.PHONY: generate
generate: er openapi ## Rewrite every generated block from its sources
	$(PYTHON) tools/docs.py generate

.PHONY: generate-models
generate-models: er openapi ## Regenerate the SQL, API and model references
	$(PYTHON) tools/docs.py generate $(MODEL_CONTRACTS)

# Code-derived reference only: this does not validate a journey for the dossier.
KF_REFERENCE := apps/knowledge-flow-backend/docs/API_REFERENCE.md

.PHONY: knowledge-flow-openapi knowledge-flow-reference check-knowledge-flow-reference
knowledge-flow-openapi:
	$(MAKE) --no-print-directory -C $(ROOT)/apps/knowledge-flow-backend generate-openapi

knowledge-flow-reference: knowledge-flow-openapi ## Generate the KF technical reference outside the validated dossier
	$(PYTHON) tools/docs.py generate $(KF_REFERENCE)

check-knowledge-flow-reference: knowledge-flow-openapi ## Check KF reference freshness (static only)
	$(PYTHON) tools/docs.py check $(KF_REFERENCE)

.PHONY: check
check: check-er openapi ## Check generated blocks, invariant references and diagram rendering
	$(PYTHON) tools/docs.py check
	$(MAKE) --no-print-directory render

.PHONY: check-models render
check-models: check-er openapi ## Check the LLM reference and its reading path (no provider calls)
	$(PYTHON) -m unittest discover -s tools -p 'test_*.py'
	$(PYTHON) tools/docs.py check $(MODEL_CONTRACTS)
	$(PYTHON) tools/docs.py links $(addprefix docs/architecture/,$(wildcard *.md))
	$(MAKE) --no-print-directory render RENDER_PAGES="$(notdir $(MODEL_PAGES))"

render: ## Render selected Markdown diagrams in disposable output
	@set -e; out=$$(mktemp -d); trap 'rm -rf $$out' EXIT; cp $(RENDER_PAGES) $$out/; \
	for f in $$out/*.md; do \
		grep -q '```mermaid' $$f || continue; \
		docker run --rm -u $$(id -u):$$(id -g) -v $$out:/data $(MERMAID_IMAGE) \
			-q -i /data/$$(basename $$f) -o /data/rendered-$$(basename $$f) >/dev/null \
			|| { echo "mermaid failed to render in $$(basename $$f)"; exit 1; }; \
	done; echo "all diagrams render"

.PHONY: help
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
