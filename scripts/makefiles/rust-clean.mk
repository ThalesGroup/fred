##@ Clean

.PHONY: clean

clean: ## Clean all build/test artifacts
	@echo "🧹 Cleaning project..."
	$(CARGO) clean
	rm -rf $(TARGET)
