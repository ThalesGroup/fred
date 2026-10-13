## Context

The frontend currently constructs `/join-free/:token`, declares that route, and exempts it from the admission-denial redirect. Fred's access-log sanitizer masks the same path. The backend API uses `/platform-access/free/{token}` and is independent of the frontend URL.

## Goals / Non-Goals

**Goals:** Keep invitation generation, routing, denial handling, authentication return, and log redaction aligned on `/join/:token`.

**Non-Goals:** Change the backend API, token format, enrollment semantics, or add a legacy route alias.

## Decisions

Replace the frontend path at its generation and routing points, and update the standalone-route recognition and log sanitizer together. Keep the backend API path and its redaction. The user confirmed that no deployment activated the old feature, so carrying an alias would add an unnecessary second public route.

## Risks / Trade-offs

- A missed path reference could break a link after sign-in or expose a token in logs. Search all non-archived references and cover route recognition, OIDC return, URL generation, and log redaction with focused tests.

## Migration Plan

Deploy the change before activating Free enrollment. No existing invitation URLs need migration. Rolling back before activation is safe; after activation, rollback would make `/join` links unusable.
