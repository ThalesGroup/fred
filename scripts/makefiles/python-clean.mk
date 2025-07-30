##@ Clean

.PHONY: clean clean-package clean-pyc clean-test

clean: clean-package clean-pyc clean-test ## Clean all build/test artifacts
	@echo "🧹 Cleaning project..."
	rm -rf $(VENV)
	rm -rf .cache .mypy_cache

clean-package: ## Clean distribution artifacts
	@echo "************ CLEANING DISTRIBUTION ************"
	rm -rf dist
	rm -rf $(TARGET)

clean-pyc: ## Clean Python bytecode
	@echo "************ CLEANING PYTHON CACHE ************"
	find . -name '*.pyc' -delete
	find . -name '*.pyo' -delete
	find . -name '*~' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +

clean-test: ## Clean test cache
	@echo "************ CLEANING TESTS ************"
	rm -rf .tox .coverage htmlcov $(TARGET)/.tested .pytest_cache
