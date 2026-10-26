.DEFAULT_GOAL := help

FIXTURE_TRANSFER_ROOT ?= target/fixture-transfer
FIXTURE_VALIDATION_ROOT ?= target/fixture-validation
RELEASE_SELECTION ?=
SELECTION_ARGS = $(if $(filter command line,$(origin RELEASE_SELECTION)),--select "$(RELEASE_SELECTION)",$(if $(RELEASE_SELECTION),--select "$(RELEASE_SELECTION)",))
PACKAGE ?=
RELEASE_DIR ?=
AUTH_MODE ?= local
DRY_RUN ?=
VERSION ?=
CHANNEL ?=
REGISTRY ?= https://registry.npmjs.org/
RELEASE_DIR_ARG = $(if $(RELEASE_DIR),--release-dir "$(RELEASE_DIR)",)
DRY_RUN_ARG = $(if $(filter 1 true yes,$(DRY_RUN)),--dry-run,)

# Every target below that shells out to npm needs the installed tree; only
# `help` and `clean` run on Node builtins alone. Declaring the dependency once
# here is what keeps a fresh clone from failing with "eslint: not found".
NPM_TARGETS := build lint format-check format-fix test pack pack-tokens pack-ui pack-iframe-sdk pack-check pack-check-tokens pack-check-ui pack-check-iframe-sdk consumer-provision consumer-provision-iframe-sdk consumer-provision-react compatibility-provision isolated-consumer host-integration browser-install browser-smoke release-check release-test fixture-transfer-create fixture-transfer-validate registry-verify prepare-release publish verify-release promote

.PHONY: help install code-quality code-quality-fix clean $(NPM_TARGETS)

$(NPM_TARGETS): node_modules

help:
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Real file target, not .PHONY: make reruns `npm ci` only when the manifests are
# newer than the tree, so the install is automatic once and a no-op afterwards.
node_modules: package.json package-lock.json
	npm ci
	@touch node_modules

install: ## Reinstall the lockfile-pinned producer dependencies from scratch
	npm ci
	@touch node_modules

build: ## Generate all frontend packages from canonical FRED inputs
	npm run build

lint: ## Lint producer scripts and tests
	npm run lint

format-check: ## Check formatting without rewriting files
	npm run format

code-quality: lint format-check ## Run all producer quality checks

format-fix: ## Rewrite formatting in place
	npm run format:fix

code-quality-fix: format-fix ## Auto-fix what code-quality flags (prettier formatting)
	@echo "Producer auto-fix tasks completed"

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

consumer-provision-iframe-sdk: ## Provision only the SDK consumer cache
	npm run consumer:provision:iframe-sdk

consumer-provision-react: ## Provision only the pinned React consumer cache
	npm run consumer:provision:ui

compatibility-provision: ## Recheck exact prior token bytes/provenance and cache them for UI-only use
	npm run release:provision:ui-baseline

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
	npm run fixture:transfer:create -- --output $(FIXTURE_TRANSFER_ROOT) $(SELECTION_ARGS)

fixture-transfer-validate: ## Verify and exercise the received fixture archives
	PLAYWRIGHT_BROWSERS_PATH=target/playwright npm run fixture:transfer:validate -- --transfer $(FIXTURE_TRANSFER_ROOT) --evidence $(FIXTURE_VALIDATION_ROOT)/final-evidence.json --stage-root $(FIXTURE_VALIDATION_ROOT)/staged $(SELECTION_ARGS)

registry-verify: ## Verify exact published coordinates (network; never local fallback)
	npm run registry:verify -- $(SELECTION_ARGS)

prepare-release: ## Build and validate one package into a portable release directory
	PLAYWRIGHT_BROWSERS_PATH=target/playwright npm run release:operation -- prepare --package "$(PACKAGE)" $(RELEASE_DIR_ARG) --registry "$(REGISTRY)"

publish: ## Publish exact prepared bytes to next (use DRY_RUN=1 for no mutation)
	npm run release:operation -- publish --package "$(PACKAGE)" $(RELEASE_DIR_ARG) --registry "$(REGISTRY)" --auth-mode "$(AUTH_MODE)" $(DRY_RUN_ARG)

verify-release: ## Verify prepared package bytes against the exact registry version
	npm run release:operation -- verify --package "$(PACKAGE)" $(RELEASE_DIR_ARG) --registry "$(REGISTRY)"

promote: ## Move CHANNEL to an existing VERSION (use DRY_RUN=1 for no mutation)
	npm run release:operation -- promote --package "$(PACKAGE)" --version "$(VERSION)" --channel "$(CHANNEL)" --registry "$(REGISTRY)" --auth-mode "$(AUTH_MODE)" $(DRY_RUN_ARG)

clean: ## Remove disposable producer output and review evidence
	node scripts/clean.mjs
