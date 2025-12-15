.PHONY: run run-geo run-tcl clean

BACKEND_ROOT := $(abspath $(CURDIR)/../../..)
UV := uv run
UVICORN := $(UV) uvicorn

GEO_APP := agentic_backend.academy.08_eco_advisor.geo_distance_service.server_mcp:app
TCL_APP := agentic_backend.academy.08_eco_advisor.tcl_transit_service.server_mcp:app

run:
	@set -euo pipefail; \
	  prefix() { label="$$1"; sed "s/^/[$${label}] /"; }; \
	  (cd $(BACKEND_ROOT) && $(UVICORN) $(GEO_APP) --host 127.0.0.1 --port 9801) 2>&1 | prefix GEO & \
	  (cd $(BACKEND_ROOT) && $(UVICORN) $(TCL_APP) --host 127.0.0.1 --port 9802) 2>&1 | prefix TCL & \
	  wait

run-geo:
	cd $(BACKEND_ROOT) && $(UVICORN) $(GEO_APP) --host 127.0.0.1 --port 9801

run-tcl:
	cd $(BACKEND_ROOT) && $(UVICORN) $(TCL_APP) --host 127.0.0.1 --port 9802

clean:
	@echo "🧹 Cleaning EcoAdvisor MCP service artifacts..."
	find $(BACKEND_ROOT)/agentic_backend/academy/08_eco_advisor -name '__pycache__' -type d -prune -exec rm -rf {} +
