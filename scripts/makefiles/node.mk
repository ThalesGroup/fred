NODE_VERSION := 24.21.0
NPM_VERSION := 11.19.0

# Check even when node_modules already exists, before any npm-backed target runs.
.PHONY: check-node
check-node:
	@required=$(NODE_VERSION); current=$$(node -p 'process.versions.node'); \
	if [ "$${current%%.*}" != "$${required%%.*}" ] || \
	   [ "$$(printf '%s\n' "$$required" "$$current" | sort -V | head -n1)" != "$$required" ]; then \
		echo "Node.js >=$(NODE_VERSION) <25 is required; found $$current. Install Node $(NODE_VERSION)." >&2; \
		exit 1; \
	fi
