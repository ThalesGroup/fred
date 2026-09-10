.DEFAULT_GOAL := help

.PHONY: help install build lint format-check code-quality test pack pack-tokens pack-ui pack-iframe-sdk pack-check pack-check-tokens pack-check-ui pack-check-iframe-sdk consumer-provision isolated-consumer browser-install browser-smoke clean

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

browser-install: ## Provision Chromium separately from browser-smoke execution
	npm run browser:install

browser-smoke: ## Run local-only browser checks against staged consumer output
	npm run test:browser

clean: ## Remove disposable producer output and review evidence
	node scripts/clean.mjs
