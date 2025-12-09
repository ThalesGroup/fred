.PHONY: run run-co2 run-traffic run-tcl run-geo

BACKEND_ROOT := $(abspath $(CURDIR)/../../..)
UV := uv run
UVICORN := $(UV) uvicorn

CO2_APP := agentic_backend.academy.08_ecoadviser.co2_estimation_service.server_mcp:app
TRAFFIC_APP := agentic_backend.academy.08_ecoadviser.traffic_service.server_mcp:app
TCL_APP := agentic_backend.academy.08_ecoadviser.tcl_service.server_mcp:app
GEO_APP := agentic_backend.academy.08_ecoadviser.geo_distance_service.server_mcp:app

run:
	@set -euo pipefail; \
	  prefix() { label="$$1"; sed "s/^/[$${label}] /"; }; \
	  (cd $(BACKEND_ROOT) && $(UVICORN) $(CO2_APP) --host 127.0.0.1 --port 9798) 2>&1 | prefix CO2 & \
	  (cd $(BACKEND_ROOT) && $(UVICORN) $(TRAFFIC_APP) --host 127.0.0.1 --port 9799) 2>&1 | prefix TRAFFIC & \
	  (cd $(BACKEND_ROOT) && $(UVICORN) $(TCL_APP) --host 127.0.0.1 --port 9800) 2>&1 | prefix TCL & \
	  (cd $(BACKEND_ROOT) && $(UVICORN) $(GEO_APP) --host 127.0.0.1 --port 9801) 2>&1 | prefix GEO & \
	  wait

run-co2:
	cd $(BACKEND_ROOT) && $(UVICORN) $(CO2_APP) --host 127.0.0.1 --port 9798

run-traffic:
	cd $(BACKEND_ROOT) && $(UVICORN) $(TRAFFIC_APP) --host 127.0.0.1 --port 9799

run-tcl:
	cd $(BACKEND_ROOT) && $(UVICORN) $(TCL_APP) --host 127.0.0.1 --port 9800

run-geo:
	cd $(BACKEND_ROOT) && $(UVICORN) $(GEO_APP) --host 127.0.0.1 --port 9801
