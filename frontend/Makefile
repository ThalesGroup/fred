


.DEFAULT_GOAL := help

VERSION ?= 0.1-dev
PROJECT_REGISTRY=registry.thalesdigital.io/tsn/projects/fred
PROJECT_NAME=fred-frontend
NODE_VERSION=22.13.0

# Docker
IMG=$(PROJECT_REGISTRY)/$(PROJECT_NAME):$(VERSION)

# Helm
HELM_ARCHIVE=./$(PROJECT_NAME)-$(VERSION).tgz

# Project id in GitLab
PROJECT_ID="74328"


##@ Build

.PHONY: check-node
check-node: ## Check if Node.js version is at least the required version
	@REQUIRED=$(NODE_VERSION); \
	CURRENT=$$(node -v | sed 's/^v//'); \
	verlte() { [ "$$1" = "$$2" ] && return 0 || [  "$$(printf '%s\n' "$$1" "$$2" | sort -V | head -n1)" = "$$1" ]; }; \
	if ! verlte "$$REQUIRED" "$$CURRENT"; then \
		echo "Node.js v$$REQUIRED or higher is required, but found v$$CURRENT. Please use the correct version."; \
		exit 1; \
	fi


.PHONY: regen-lockfile
regen-lockfile: check-node ## Regenerate package-lock.json inside Docker
	docker run --rm -it -v $(CURDIR):/src -w /src node:22.13.0 bash -c "rm -rf node_modules package-lock.json && npm install"

.PHONY: node_modules
node_modules: check-node package.json
	npm install

.PHONY: build
build: check-node node_modules ## Build the ui using npm run build
	npm run build

.PHONY: helm-package
helm-package: ## Package the Helm chart into a chart archive
	helm package helm-chart/

.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build --no-cache -t $(IMG) -f dockerfiles/Dockerfile-dev .

##@ Run

.PHONY: run
run: check-node node_modules ## Run fred-ui front-end locally
	npm run dev

.PHONY: docker-run
docker-run: ## Docker run
	docker run -it --rm \
      -v ~/.kube/config:/kube/config \
      --network=host \
      --name fred-ui \
      $(IMG)

##@ Dev

.PHONY: format
format: ## Use prettier to format all codebase
	npx prettier . --write

##@ Clean

.PHONY: clean
clean: ## Clean requirements and build files
	rm -rf $(CURDIR)/build
	rm -rf $(CURDIR)/dist
	rm -rf $(CURDIR)/node_modules
	rm -rf node_modules

.PHONY: clean-docker
clean-docker: ## Clean up Docker-related artifacts
	docker rm -f fred-frontend || true
	docker image prune -f

.PHONY: full-clean
full-clean: clean clean-docker ## Perform a full cleanup

##@ Image and Helm chart publishing

.PHONY: docker-push
docker-push: ## Push the docker image
	docker push $(IMG)


.PHONY: helm-push
helm-push: ## Push the Helm chart to the project registry
	curl --fail-with-body --request POST \
         --form "chart=@${HELM_ARCHIVE}" \
         --user ${GITLAB_USER}:${GITLAB_TOKEN} \
         https://gitlab.thalesdigital.io/api/v4/projects/${PROJECT_ID}/packages/helm/api/release/charts



##@ Help

.PHONY: help
help: ## Print help
	@awk 'BEGIN {FS = ":.*##"; printf "\033[36m\033[0m\n"} /^[ 0-9a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)