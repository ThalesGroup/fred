FROM docker:28.5.0-cli AS docker-cli

FROM python:3.12-slim

ARG TARGETARCH=amd64
ARG KUBECTL_VERSION=v1.34.1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSLo /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && curl -fsSLo /tmp/kubectl.sha256 \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256" \
    && echo "$(cat /tmp/kubectl.sha256)  /usr/local/bin/kubectl" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/kubectl \
    && rm /tmp/kubectl.sha256

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY libs/fred-sdk /build/fred-sdk
COPY apps/sandbox-broker /build/sandbox-broker
# The broker imports only fred_sdk.contracts.sandbox; avoid the full agent dependency tree.
RUN pip install --no-cache-dir "asyncpg>=0.31" "fastapi>=0.115" "httpx>=0.28" "uvicorn>=0.35" \
    && pip install --no-cache-dir --no-deps /build/fred-sdk /build/sandbox-broker \
    && useradd --uid 65532 --create-home broker

USER 65532:65532
EXPOSE 8443
CMD ["uvicorn", "sandbox_broker.main:app", "--host", "0.0.0.0", "--port", "8443", "--ssl-certfile", "/tls/tls.crt", "--ssl-keyfile", "/tls/tls.key"]
