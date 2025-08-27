# Agentic → Knowledge Flow authentication (Keycloak) — Quick User Guide

Use this guide to verify that **every environment** (dev, staging, prod) can reuse the same Keycloak clients to let the **Agentic backend** call the **Knowledge Flow** backend securely — and to explain why *Knowledge Flow itself also needs a client secret*.

---

## Topology & Clients

- **Keycloak realm:** `app`  
  (example URL: `http://app-keycloak:8080/realms/app`)

- **Shared clients (created once by platform admins):**
  - **`agentic`** — *caller identity* (type: **confidential**, **Service accounts: ON**)  
    Used by the Agentic backend to mint **client-credentials** tokens and call Knowledge Flow.
  - **`knowledge-flow`** — *API audience & service identity for Knowledge Flow* (type: **confidential**; see below for Service accounts)  
    - Acts as the **audience** (and/or `azp`) your Knowledge Flow service expects in incoming tokens.
    - Also acts as the **service identity** Knowledge Flow uses to make **internal, service-to-service (B2B) calls** (e.g., in-process ASGI client, background jobs, MCP servers invoking HTTP tools).  
      For these internal calls, **Service accounts must be ON** so Knowledge Flow can mint its own client-credentials tokens.

> TL;DR  
> - If Knowledge Flow *never* needs to mint tokens to call anything (including itself), Service accounts for `knowledge-flow` may be left **OFF**.  
> - In our setup we **do** use an internal ASGI/B2B client, so **turn Service accounts ON** for `knowledge-flow`.

- Your web UI keeps using its existing `app` web client. Nothing to change there.

---

## Environment Variables (by component)

### Knowledge Flow service (the API being called)
Required so it can **mint short-lived service tokens** for internal B2B/ASGI calls and avoid 401s:

