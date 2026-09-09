.DEFAULT_GOAL := help

.PHONY: help install build lint format-check code-quality test pack pack-check isolated-consumer browser-install browser-smoke clean

help:
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the lockfile-pinned producer dependencies
	npm ci

build: ## Generate the design-token package from canonical FRED inputs
	npm run build

lint: ## Lint producer scripts and tests
	npm run lint

format-check: ## Check formatting without rewriting files
	npm run format

code-quality: lint format-check ## Run all producer quality checks

test: ## Run offline producer unit tests
	npm test

pack: ## Build and create the design-token tarball
	npm run pack

pack-check: ## Build, pack, validate, and retain archive evidence
	npm run pack:check

isolated-consumer: ## Install the tarball offline outside the checkout and build it
	npm run test:consumer

browser-install: ## Provision Chromium separately from browser-smoke execution
	npm run browser:install

browser-smoke: ## Run local-only browser checks against staged consumer output
	npm run test:browser

clean: ## Remove disposable producer output and review evidence
	node scripts/clean.mjs
