CARGO ?= $(HOME)/.cargo/bin/cargo

.PHONY: code-quality test
code-quality: ## Check the pure page-format library
	$(CARGO) fmt -p fred-wiki --check
	$(CARGO) clippy --locked -p fred-wiki --all-targets -- -D warnings
	$(CARGO) tree --locked -p fred-wiki -e normal

test: ## Run page-format regressions without services
	$(CARGO) test --locked -p fred-wiki
