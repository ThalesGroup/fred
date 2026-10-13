include ../../scripts/makefiles/config/INFO-fred-manager.mk

# === Rust Utility ===
include ../../scripts/makefiles/rust-vars.mk
include ../../scripts/makefiles/rust-deps.mk
include ../../scripts/makefiles/rust-run.mk
include ../../scripts/makefiles/rust-test.mk
include ../../scripts/makefiles/rust-code-quality.mk
include ../../scripts/makefiles/rust-clean.mk
include ../../scripts/makefiles/help.mk

##@ Dev Helpers

ORG_NAME ?=
ORG_ADMIN ?=

.PHONY: create-org
create-org: dev ## Create an organization and its first admin (usage: make create-org ORG_NAME=TSN ORG_ADMIN=<keycloak sub>)
	@if [ -z "$(ORG_NAME)" ] || [ -z "$(ORG_ADMIN)" ]; then \
		echo "❌ Usage: make create-org ORG_NAME=<name> ORG_ADMIN=<keycloak sub>"; \
		exit 1; \
	fi
	$(CARGO) run -- create-org "$(ORG_NAME)" "$(ORG_ADMIN)"

##@ Docker

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build \
		-f $(DOCKERFILE_PATH) \
		-t $(IMAGE_FULL) \
		$(DOCKER_CONTEXT)

.PHONY: docker-push
docker-push: ## Push the Docker image
	docker push $(IMAGE_FULL)
