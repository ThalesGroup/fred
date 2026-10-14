# Architecture dossier: regenerate its generated blocks and check it against the code.
# Postgres, tbls and mermaid-cli run in throwaway containers; nothing is installed.

PYTHON          ?= python3
POSTGRES_IMAGE  ?= mirror.gcr.io/postgres:15.12-alpine3.20
TBLS_IMAGE      ?= ghcr.io/k1low/tbls:v1.96.0
MERMAID_IMAGE   ?= minlag/mermaid-cli:11.17.0
ROOT            := $(realpath ../..)

# One entity-relationship diagram per component, from its migrations.
ER_COMPONENTS   ?= fred-manager

.DEFAULT_GOAL := help

##@ Architecture dossier

.PHONY: er
er: ## Regenerate generated/<component>.er.mmd from each component's migrations
	@set -e; for c in $(ER_COMPONENTS); do \
		pg=docs-er-$$c-$$$$; \
		trap 'docker rm -f $$pg >/dev/null 2>&1 || true' EXIT; \
		docker run -d --name $$pg -e POSTGRES_PASSWORD=docs -p 127.0.0.1::5432 $(POSTGRES_IMAGE) >/dev/null; \
		until docker exec $$pg psql -U postgres -h 127.0.0.1 -c 'select 1' >/dev/null 2>&1; do sleep 1; done; \
		cat $(ROOT)/apps/$$c/migrations/*.sql | docker exec -i $$pg psql -U postgres -q -v ON_ERROR_STOP=1; \
		addr=$$(docker port $$pg 5432/tcp | head -n1); \
		docker run --rm --network host $(TBLS_IMAGE) out -t mermaid \
			"postgres://postgres:docs@$$addr/postgres?sslmode=disable" > generated/$$c.er.mmd; \
		$(PYTHON) tools/docs.py tidy-er docs/architecture/generated/$$c.er.mmd; \
		docker rm -f $$pg >/dev/null; echo "generated/$$c.er.mmd"; \
	done

.PHONY: generate
generate: er ## Rewrite every generated block from its sources
	$(PYTHON) tools/docs.py generate

.PHONY: check
check: er ## Fail if a generated block is stale, an invariant lacks a test, or a diagram does not render
	$(PYTHON) tools/docs.py check
	@set -e; out=$$(mktemp -d); trap 'rm -rf $$out' EXIT; cp *.md $$out/; \
	for f in $$out/*.md; do \
		grep -q '```mermaid' $$f || continue; \
		docker run --rm -u $$(id -u):$$(id -g) -v $$out:/data $(MERMAID_IMAGE) \
			-q -i /data/$$(basename $$f) -o /data/rendered-$$(basename $$f) >/dev/null \
			|| { echo "mermaid failed to render in $$(basename $$f)"; exit 1; }; \
	done; echo "all diagrams render"

.PHONY: help
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
