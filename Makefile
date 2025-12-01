CODE_QUALITY_DIRS := fred-core agentic-backend knowledge-flow-backend

##@ Code quality

.PHONY: code-quality
code-quality: ## Run code quality checks in all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Running code-quality in $$dir ************"; \
		$(MAKE) -C $$dir code-quality; \
	done

.PHONY: code-quality-fix
code-quality-fix: ## Auto-fix formatting/imports/linting in all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Running code-quality fixes in $$dir ************"; \
		$(MAKE) -C $$dir lint-fix import-order-fix format-fix; \
	done

.PHONY: clean
clean: ## Clean all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Cleaning $$dir ************"; \
		$(MAKE) -C $$dir clean; \
	done
	
.PHONY: dev
dev:  ## Start development environment in all submodules
	@set -e; \
	for dir in $(CODE_QUALITY_DIRS); do \
		echo "************ Starting dev environment in $$dir ************"; \
		$(MAKE) -C $$dir dev & \
	done; \
	wait
		
include scripts/makefiles/help.mk
