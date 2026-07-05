.DEFAULT_GOAL := help

# Rendering conventions understood by the `help` target below:
#   ##@ <text>   -> section header (bold), groups the targets under it
#   <target>: ## <text> -> a target row: name in cyan + its description
#   ##> <text>   -> free-text line (indented, no target), for short notes or
#                   workflow hints inside a section. Opt-in: only Makefiles that
#                   use `##>` show these; others are unaffected.

##@ Help

help:  ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\n\033[1mAvailable targets:\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } /^##>/ { printf "  %s\n", substr($$0, 4) } ' $(MAKEFILE_LIST)
