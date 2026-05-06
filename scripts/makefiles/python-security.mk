##@ Security

_SECURITY_MK_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: check-route-security
check-route-security: dev ## Check if all FastAPI routes are secured with authentication
	$(PYTHON) $(_SECURITY_MK_DIR)/../check_route_security.py