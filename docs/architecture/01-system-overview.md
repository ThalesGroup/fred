# 1. System overview

## Product purpose and users

## System context and external services

## Responsibilities and component boundaries

Fred's application release comprises five independently supervised processes using
three images. Manager serves governance, identity-facing admission, spaces, folders
and authorization; its worker executes manager-owned lifecycle work. Knowledge Flow
serves its existing content APIs and ingestion work through an API and a worker.
The frontend presents the shared Fred UI and routes requests to application APIs.
The deployment contract names the Rust API and worker `control-plane-backend` and
`control-plane-worker`; both use the `control-plane-backend` image built from manager.

PostgreSQL, OpenFGA, Keycloak, Temporal and content/search storage have independent
lifecycles. Replacing application processes does not recreate these services or
transfer ownership of their data. Manager and Knowledge Flow keep their existing
data and authorization boundaries. Packaging them together does not migrate
Knowledge Flow content into manager.

## Shared vocabulary

## Architectural quality goals
