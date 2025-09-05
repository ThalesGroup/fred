##@ Security

.PHONY: check-route-security
check-route-security: dev ## Check if all FastAPI routes are secured with authentication
	$(PYTHON) ../scripts/check_route_security.py