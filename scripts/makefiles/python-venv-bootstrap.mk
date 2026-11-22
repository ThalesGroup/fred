# Needs:
# - PIP
# - TARGET
# - VENV

##@ Virtualenv Bootstrap

# Keep aligned with the Docker images and setup-uv steps.
UV_VERSION := 0.13.5
UV_BOOTSTRAP_VENV ?= $(VENV)

$(TARGET)/.uv-venv-created:
	@echo "🔧 Creating virtualenv..."
	mkdir -p $(TARGET)
	flock $(TARGET)/.venv.lock sh -c 'test -f $@ || (python3 -m venv $(UV_BOOTSTRAP_VENV) && touch $@)'

$(TARGET)/.uv-installed: $(TARGET)/.uv-venv-created _check-uv-version
	@flock $(TARGET)/.uv.lock sh -ec '\
		if ! test -f "$@"; then \
			$(PIP) install --upgrade pip setuptools wheel; \
		fi; \
		if ! test -f "$@" || ! test "$$($(UV) --version 2>/dev/null | cut -d " " -f 2)" = "$(UV_VERSION)"; then \
			$(PIP) install "uv==$(UV_VERSION)"; \
			touch "$@"; \
		fi'

.PHONY: _check-uv-version
_check-uv-version:
