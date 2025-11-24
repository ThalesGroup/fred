# Minimal Makefile to set up and run the standard MCP Server
# --------------------------------------------------
# Simply run `make server` to handle the full workflow (install + run).

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
UVICORN := $(PYTHON) -m uvicorn
PORT := 9797
HOST := 127.0.0.1
APP_MODULE := minimal_mcp_server.server_mcp:app

.PHONY: help venv install server clean

help:
	@echo ""
	@echo "Usage:"
	@echo "  make install  # Set up environment and install dependencies."
	@echo "  make run   # Run the server (includes install automatically)."
	@echo "  make clean    # Remove the virtual environment and cache."
	@echo ""

# 1. Create the virtual environment if it doesn't exist
venv:
	@echo "Ensuring virtual environment is created..."
	@test -d $(VENV_DIR) || python3 -m venv $(VENV_DIR)

# 2. Install dependencies (Requires venv)
install: venv
	@echo "Installing/Upgrading dependencies in $(VENV_DIR)..."
	$(PYTHON) -m pip install --upgrade pip
	# Install FastAPI, Uvicorn, and the MCP SDK with FastAPI extras
	$(PYTHON) -m pip install fastapi uvicorn "mcp[fastapi]"

# 3. Run the server (Requires install)
run: install
	@echo "🚀 Starting standard MCP server on http://$(HOST):$(PORT)"
	@echo "Using module: $(APP_MODULE)"
	$(UVICORN) $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

# 4. Clean up: removes the virtual environment folder
clean:
	@echo "Removing virtual environment ($(VENV_DIR)) and cache files..."
	@rm -rf $(VENV_DIR)
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true