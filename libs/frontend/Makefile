.DEFAULT_GOAL := help

FIXTURE_TRANSFER_ROOT ?= target/fixture-transfer
FIXTURE_VALIDATION_ROOT ?= target/fixture-validation

.PHONY: help install build lint format-check code-quality test pack pack-tokens pack-ui pack-iframe-sdk pack-check pack-check-tokens pack-check-ui pack-check-iframe-sdk consumer-provision isolated-consumer host-integration browser-install browser-smoke release-check release-test fixture-transfer-create fixture-transfer-validate release-candidate release-verify-evidence registry-verify clean

help:
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the lockfile-pinned producer dependencies
	npm ci

build: ## Generate all frontend packages from canonical FRED inputs
	npm run build

lint: ## Lint producer scripts and tests
	npm run lint

format-check: ## Check formatting without rewriting files
	npm run format

code-quality: lint format-check ## Run all producer quality checks

test: ## Run offline producer unit tests
	npm test

pack: ## Build and create all package tarballs
	npm run pack

pack-tokens: ## Build and create the design-token tarball
	npm run pack:tokens

pack-ui: ## Build and create the UI tarball
	npm run pack:ui

pack-iframe-sdk: ## Build and create the iframe SDK tarball
	npm run pack:iframe-sdk

pack-check: ## Build, pack, validate all archives, and retain evidence
	npm run pack:check

pack-check-tokens: ## Validate the design-token tarball contract
	npm run pack:check:tokens

pack-check-ui: ## Validate the UI tarball contract
	npm run pack:check:ui

pack-check-iframe-sdk: ## Validate the iframe SDK tarball contract
	npm run pack:check:iframe-sdk

consumer-provision: ## Populate the pinned consumer caches (network allowed)
	npm run consumer:provision

isolated-consumer: ## Install actual tarballs offline in isolated consumers and build
	npm run test:consumer

host-integration: ## Exercise the actual SDK tarball with FRED's production host page
	npm run test:host-integration

browser-install: ## Provision Chromium separately from browser-smoke execution
	npm run browser:install

browser-smoke: ## Run local-only browser checks against staged consumer output
	npm run test:browser

release-check: ## Validate release contracts and dependency boundaries
	npm run release:check

release-test: ## Run controlled release tooling tests without registry access
	npm run release:test

fixture-transfer-create: ## Produce the three-archive fixture transfer for this run
	npm run fixture:transfer:create -- --output $(FIXTURE_TRANSFER_ROOT)

fixture-transfer-validate: ## Verify and exercise the received fixture archives
	PLAYWRIGHT_BROWSERS_PATH=target/playwright npm run fixture:transfer:validate -- --transfer $(FIXTURE_TRANSFER_ROOT) --evidence $(FIXTURE_VALIDATION_ROOT)/final-evidence.json --stage-root $(FIXTURE_VALIDATION_ROOT)/staged

release-candidate: ## Build evidence under an explicitly selected contract
	npm run release:candidate --

release-verify-evidence: ## Recompute integrity for an existing candidate set
	npm run release:verify-evidence --

registry-verify: ## Verify exact published coordinates (network; never local fallback)
	npm run registry:verify --

clean: ## Remove disposable producer output and review evidence
	node scripts/clean.mjs
