# Needs:
# - PIP
# - TARGET
# - VENV

##@ Virtualenv Bootstrap

$(TARGET)/.venv-created:
	@echo "🔧 Creating virtualenv..."
	mkdir -p $(TARGET)
	flock $(TARGET)/.venv.lock sh -c 'test -f $@ || (python3 -m venv $(VENV) && touch $@)'

$(TARGET)/.uv-installed: $(TARGET)/.venv-created
	@echo "📦 Installing uv..."
	flock $(TARGET)/.uv.lock sh -c 'test -f $@ || ($(PIP) install --upgrade pip setuptools wheel && $(PIP) install uv && touch $@)'
