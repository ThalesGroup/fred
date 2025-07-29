##@ Code quality

.PHONY: lint
lint: ## Run the linter (ruff) 
	@echo "************ Executing Ruff linter ************"
	$(UV) run ruff check

.PHONY: lint-fix
lint-fix: ## Run the linter (ruff) to fix all the auto fixable linter error
	@echo "************ Executing Ruff linter and apply fix if possible ************"
	$(UV) run ruff check --fix

.PHONY: format
format: ## Run the formatter (ruff)
	@echo "************ Executing Ruff formatter ************"
	$(UV) run ruff format

.PHONY: sast
sast: ## Run bandit
	@echo "************ Executing Ruff formatter with rules B101 (assert_used) and B108 (hardcoded_tmp_directory) ignored ************"
	$(UV) run bandit -r app -s B101,B108

.PHONY: type-check
type-check: ## Run type checker (basedpyright)
	@echo "************ Executing Basedpyright type checker ************"
	$(UV) run basedpyright

.PHONY: code-quality
code-quality: ## Run all pre-commit checks
	@echo "************ Executing pre-commit ************"
	$(UV) run pre-commit run --all-files
