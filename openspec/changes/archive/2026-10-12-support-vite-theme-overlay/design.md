# Design

## Context

See proposal.md. The Docker entrypoint already implements bounded curl downloads,
SigV4 credentials, archive extraction, validation and staging. Vite currently
serves `public/` directly. The frontend Makefile reads `config/.env`, but only
forwards application-hosting settings to the development process.

## Goals / Non-Goals

**Goals:** share installation behavior, preserve the checkout, and keep S3
credentials on the server. Support the existing VS Code frontend task.

**Non-Goals:** a theme editor, storage polling, nested ZIPs or per-theme branding
properties. No backend or migration changes.

## Decisions

- Extract the existing shell installer into one reusable script consumed by
  Docker and Vite. Keep its curl/unzip/jq checks rather than implementing a
  second archive parser and SigV4 signer in Node.
- At Vite startup, install into a temporary directory and register an overlay
  middleware before stock public assets. Serve only supported files, enforce
  root containment, set the proper MIME types and no-cache, and fall through
  to stock files when an override is missing. Remove the directory on shutdown.
  Copying into `public/` was rejected because it dirties the checkout and leaves
  stale branding when a theme is disabled.
- Preserve explicit shell settings through Make and let Vite parse theme file
  values as dotenv, rather than exporting Make-parsed quotes or dollar escapes.
  Document `config/.env` and never introduce a `VITE_` secret.
- Keep restart-to-activate semantics, matching the existing container contract.

## Risks / Trade-offs

- Local shell dependencies: check curl, unzip and jq with actionable errors.
- Installer extraction could regress Docker: run existing archive smoke coverage
  and focused local tests against the shared installer.
- Overlay path handling: test encoded traversal, unsupported routes and fallback.
- Cleanup and startup failures: never expose a partially installed directory.

## Migration Plan

Configure the same URL in local `config/.env` and deployment environment, using
`localhost:8333` locally and the internal SeaweedFS hostname in Docker. Restart
the frontend. Unset the URL to return to stock behavior.
