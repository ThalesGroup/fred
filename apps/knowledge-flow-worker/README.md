# Knowledge Flow worker

Install this application independently with `make dev`. Run all four Temporal roles with `make run`, or one with `make run-worker-role ROLE=common|fast|medium|rich`. Configure it through `CONFIG_FILE` and `ENV_FILE`; credentials remain environment references.

The worker owns extraction, processing profiles, generation writes and Temporal workflows. It has no incoming HTTP security configuration. The API reads published artifacts and search projections from its own application and image.

Production: `make docker-build`; optional PDF implementation: `docker build -f apps/knowledge-flow-worker/dockerfiles/Dockerfile-prod --build-arg INSTALL_PYMUPDF=true -t knowledge-flow-worker-pymupdf:local .` from the repository root. PyMuPDF selection changes only worker configuration and images. Keep its dependency license notices.

Roles `common`, `extraction-fast`, `extraction-medium`, `extraction-rich`, workflow/activity names, queues and processing profiles are unchanged. Drain active ingestion before changing processor configuration. Schema and deployment validation remain to be performed by the developer.
