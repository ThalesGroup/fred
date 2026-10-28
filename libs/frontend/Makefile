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

# Preserve every public release value as opaque environment data. `$(value ...)`
# prevents inherited and command-line text from being expanded as Make syntax,
# and `override` prevents callers from replacing the internal capture directly.
override FRED_RELEASE_PACKAGE := $(value PACKAGE)
override FRED_RELEASE_RELEASE_DIR := $(value RELEASE_DIR)
override FRED_RELEASE_AUTH_MODE := $(value AUTH_MODE)
override FRED_RELEASE_DRY_RUN := $(value DRY_RUN)
override FRED_RELEASE_REGISTRY := $(value REGISTRY)
override FRED_RELEASE_VERSION := $(value VERSION)
override FRED_RELEASE_CHANNEL := $(value CHANNEL)
export FRED_RELEASE_PACKAGE FRED_RELEASE_RELEASE_DIR FRED_RELEASE_AUTH_MODE
export FRED_RELEASE_DRY_RUN FRED_RELEASE_REGISTRY FRED_RELEASE_VERSION
export FRED_RELEASE_CHANNEL
unexport PACKAGE RELEASE_DIR AUTH_MODE DRY_RUN REGISTRY VERSION CHANNEL

# Ordinary npm-backed targets need the installed tree. Release operations are
# separate because their built-in-only preflight must reject bad inputs (and,
# for preparation, a wrong Node/npm pair) before dependency installation.
NPM_TARGETS := build lint format-check format-fix test pack pack-tokens pack-ui pack-iframe-sdk pack-check pack-check-tokens pack-check-ui pack-check-iframe-sdk consumer-provision consumer-provision-iframe-sdk consumer-provision-react compatibility-provision isolated-consumer host-integration browser-install browser-smoke release-check release-test fixture-transfer-create fixture-transfer-validate registry-verify
RELEASE_TARGETS := prepare-release publish verify-release promote

.PHONY: help install code-quality code-quality-fix clean $(NPM_TARGETS) $(RELEASE_TARGETS)

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

# Lockfile-pinned consumer caches, provisioned like node_modules: once, then
# again only when a fixture lockfile changes. The tests themselves stay offline.
target/react-consumer-cache: fixtures/react-consumer/package-lock.json | node_modules
	npm run consumer:provision:ui
	@touch $@

target/iframe-sdk-consumer-cache: fixtures/iframe-sdk-consumer/package-lock.json | node_modules
	npm run consumer:provision:iframe-sdk
	@touch $@

test: node_modules target/react-consumer-cache target/iframe-sdk-consumer-cache ## Run offline producer unit tests
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
	node scripts/release-preflight.mjs prepare
	$(MAKE) node_modules
	PLAYWRIGHT_BROWSERS_PATH=target/playwright node scripts/npm-release.mjs prepare

publish: ## Publish exact prepared bytes to next (use DRY_RUN=1 for no mutation)
	node scripts/release-preflight.mjs publish
	$(MAKE) node_modules
	node scripts/npm-release.mjs publish

verify-release: ## Verify prepared package bytes against the exact registry version
	node scripts/release-preflight.mjs verify
	$(MAKE) node_modules
	node scripts/npm-release.mjs verify

promote: ## Move CHANNEL to an existing VERSION (use DRY_RUN=1 for no mutation)
	node scripts/release-preflight.mjs promote
	$(MAKE) node_modules
	node scripts/npm-release.mjs promote

clean: ## Remove disposable producer output and review evidence
	node scripts/clean.mjs
