# Needs:
# - CARGO
# - ENV_FILE (CONFIG_FILE and secrets; address and port come from the configuration)
# And `dev` rule (from `rust-deps.mk`)

CARGO_RUN_OPTIONS ?=

##@ Run

.PHONY: run-local
run-local: ## Run the app assuming dependencies already exist
	$(CARGO) run ${CARGO_RUN_OPTIONS} -- serve

.PHONY: run
run: dev run-local ## run the app, installing dependencies if needed

.PHONY: run-release
run-release: CARGO_RUN_OPTIONS = --release
run-release: run ## run the app with an optimized build
