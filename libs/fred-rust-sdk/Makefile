CARGO ?= $(HOME)/.cargo/bin/cargo

.PHONY: code-quality test
code-quality: ## Check formatting and lint every SDK target
	$(CARGO) fmt -p fred-rust-sdk --check
	$(CARGO) clippy --locked -p fred-rust-sdk --all-targets -- -D warnings

test: ## Run the extracted authentication regressions offline
	$(CARGO) test --locked -p fred-rust-sdk
