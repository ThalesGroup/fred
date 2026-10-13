# Needs:
# - CARGO
# - PROTOC
# - TARGET

##@ Dependency Management

$(TARGET)/.fetched: Cargo.toml Cargo.lock
	@test -x "$(CARGO)" || { echo "❌ cargo not found at $(CARGO). Install rustup: https://rustup.rs"; exit 1; }
	@test -x "$(PROTOC)" || { echo "❌ protoc not found at $(PROTOC). Set PROTOC or install protobuf-compiler."; exit 1; }
	$(CARGO) fetch --locked
	@mkdir -p $(TARGET) && touch $@

.PHONY: dev
dev: $(TARGET)/.fetched ## Install from compiled lock
	@echo "✅ Dependencies fetched using cargo."

.PHONY: update
update: ## Re-resolve and update all dependencies for the dev environment
	$(CARGO) update
	@mkdir -p $(TARGET) && touch $(TARGET)/.fetched
