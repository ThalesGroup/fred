BASELINE_DIR ?= $(CURDIR)/.baseline

BANDIT_BASELINE_FILE ?= ${BASELINE_DIR}/bandit-baseline.json
DETECT_SECRET_BASELINE_FILE ?= ${BASELINE_DIR}/detect-secret-baseline.json
BASEDPYRIGHT_BASELINE_FILE ?= ${BASELINE_DIR}/basedpyright-baseline.json

BANDIT_IGNORED_RULES ?= B101,B108

##@ Code quality

.PHONY: lint
lint: ## Run the linter (ruff)
	@echo "************ Executing Ruff linter ************"
	$(UV) run ruff check

.PHONY: lint-fix
lint-fix: ## Run the linter (ruff) to fix all the auto fixable linter error
	@echo "************ Executing Ruff linter and apply fix if possible ************"
	$(UV) run ruff check --fix

.PHONY: import-order
import-order: ## Run the formatter (ruff) to check import order
	@echo "************ Executing Ruff check for import order ************"
	$(UV) run ruff check --select I

.PHONY: import-order-fix
import-order-fix: ## Run the formatter (ruff) to fix import order
	@echo "************ Executing Ruff check to fix import order ************"
	$(UV) run ruff check --select I --fix

.PHONY: format
format: ## Run the formatter (ruff)
	@echo "************ Executing Ruff formatter ************"
	$(UV) run ruff format

.PHONY: sast
sast: ## Run bandit
	@echo "************ Executing Bandit with rules ${BANDIT_IGNORED_RULES} ingored (B101: assert_used, B108: hardcoded_tmp_directory) ************"
	$(UV) run bandit \
		-r ${PY_PACKAGE} \
		-s ${BANDIT_IGNORED_RULES} \
		--baseline ${BANDIT_BASELINE_FILE}

.PHONY: detect-secret
detect-secret: ## Run a secret detection tool
	cd .. && git ls-files -z ${CURDIR} | xargs -0 ${VENV}/bin/detect-secrets-hook --baseline ${DETECT_SECRET_BASELINE_FILE}

.PHONY: type-check
type-check: ## Run type checker (basedpyright)
	@echo "************ Executing Basedpyright type checker ************"
	$(UV) run basedpyright --baselinefile ${BASEDPYRIGHT_BASELINE_FILE}

.PHONY: code-quality
code-quality: lint format sast detect-secret type-check ## Run all code quality checks
	@echo "************ All code quality checks completed ************"

# ------------------------------------------------------------
##@ Code quality - baselines

${BASELINE_DIR}:
	mkdir -p ${BASELINE_DIR}

.PHONY: baseline-sast
baseline-sast: ${BASELINE_DIR} ## Set bandit baseline
	$(UV) run bandit \
		-r ${PY_PACKAGE} \
		-s ${BANDIT_IGNORED_RULES} \
		-f json \
		-o ${BANDIT_BASELINE_FILE}

.PHONY: baseline-detect-secret
baseline-detect-secret: ${BASELINE_DIR} ## Set detect-secrets baseline
	cd .. && ${VENV}/bin/detect-secrets scan $(CURDIR) > ${DETECT_SECRET_BASELINE_FILE} 

.PHONY: baseline-type-check
baseline-type-check: ${BASELINE_DIR} ## Set basedpyright baseline
	${UV} run basedpyright --baselinefile ${BASEDPYRIGHT_BASELINE_FILE} --writebaseline 

.PHONY: baseline
baseline: format ## Format code and set all baselines
	-$(MAKE) baseline-sast
	-$(MAKE) baseline-detect-secret
	-$(MAKE) baseline-type-check


# ------------------------------------------------------------
# One time setup

# To add the required python dependencies to the uv project
add-dev-deps:
	@echo "Adding linter and formater"
	${UV} add --dev ruff
	@echo "Adding SAST"
	${UV} add --dev bandit[baseline]
	@echo "Adding secret detection"
	${UV} add --dev detect-secrets
	@echo "Adding type checker"
	${UV} add --dev basedpyright
