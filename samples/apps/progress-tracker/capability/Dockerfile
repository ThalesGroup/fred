# Adds this capability to an existing agents image.
#
# Installing the package IS the registration -- the pod discovers it at boot
# through the `fred.capabilities` entry point in pyproject.toml, so nothing
# here edits Fred's own Dockerfile or its dependency list.
ARG BASE_IMAGE=ghcr.io/thalesgroup/fred-agent/fred-agents:0.2
FROM ${BASE_IMAGE}

USER root
COPY . /tmp/capability
RUN /app/venv/bin/pip install --no-cache-dir /tmp/capability && rm -rf /tmp/capability
USER 1000
