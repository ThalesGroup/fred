##@ Code quality

.PHONY: lint
lint: dev ## Run the linter (clippy)
	@echo "************ Executing Clippy linter ************"
	$(CARGO) clippy --all-targets -- -D warnings

.PHONY: lint-fix
lint-fix: dev ## Run the linter (clippy) to fix all the auto fixable linter error
	@echo "************ Executing Clippy linter and apply fix if possible ************"
	$(CARGO) clippy --all-targets --fix --allow-dirty --allow-staged

.PHONY: format
format: dev ## Run the formatter (rustfmt) to check for format errors
	@echo "************ Executing Rustfmt formatter ************"
	$(CARGO) fmt --check

.PHONY: format-fix
format-fix: dev ## Run the formatter (rustfmt) to fix format errors
	@echo "************ Executing Rustfmt formatter ************"
	$(CARGO) fmt

.PHONY: code-quality-fix
code-quality-fix: dev lint-fix format-fix ## Auto-fix formatting/linting
	@echo "************ All auto-fix code quality checks completed ************"

.PHONY: code-quality
code-quality: dev lint format ## Run all code quality checks
	@echo "************ All code quality checks completed ************"
