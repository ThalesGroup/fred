# Minimal Makefile to set up and run the simulated IoT MCP server

VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
UVICORN := $(PYTHON) -m uvicorn
PORT := 9798
HOST := 127.0.0.1
APP_MODULE := iot_tracking_mcp_server.server_mcp:app

.PHONY: help venv install run server clean

help:
	@echo ""
	@echo "Usage:"
	@echo "  make install  # Set up environment and install dependencies"
	@echo "  make run      # Run the IoT MCP server (includes install)"
	@echo "  make clean    # Remove the virtual environment and cache"
	@echo ""

venv:
	@test -d $(VENV_DIR) || python3 -m venv $(VENV_DIR)

install: venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install fastapi uvicorn "mcp[fastapi]"

run server: install
	$(UVICORN) $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

clean:
	@rm -rf $(VENV_DIR)
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true

