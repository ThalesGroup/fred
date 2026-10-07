## Why

The frontend follows each active task with its own long-lived SSE connection.
Browsers allow six HTTP/1.1 connections per origin, and Fred is served over
HTTP/1.1: the frontend nginx listens in plain HTTP behind the deployment's
nginx. An import of more than a few files therefore fills the pool:

- every other request of the page (lists, searches, chat) waits until a task
  finishes. On 2026-10-03, the API received about **one request per minute**
  from 03:48 to 03:51, each one arriving at the second an ingestion completed;
- a stream request that waits longer than the access token's lifetime is
  refused with a 401, and the stream gives up for good: files stay on
  "Waiting…" until a reload (#2940).

Following progress does not need a connection per task. A periodic batched read
of the tasks being followed uses one short request per backend, refreshes its
token like every other API call, and cannot block the page.

Tracked by [GitHub issue #2940](https://github.com/ThalesGroup/fred/issues/2940).

## What Changes

- **Backend (`fred-core`, served by Knowledge Flow and Control Plane):**
  `GET /tasks?scope=user` accepts a repeated `task_id` parameter (at most 50
  values). With it, the response holds the caller's own tasks among those ids,
  **terminal ones included**. Without it, behaviour is unchanged.
- **Frontend:** one polling loop replaces `useTaskSseManager`. While at least
  one followed task is active, it reads the states of the active tasks in
  rounds through the generated API clients: batches of 50, one read at a time,
  then a 5 s pause. It applies them to the existing task store.
- **Explicit "untracked" outcome:** a task the server no longer returns is
  marked untracked. It is never shown as succeeded or failed. The import panel
  says that following stopped, and the document row falls back to the
  document's own status.
- **Generated clients send query arrays as repeated keys** (`a=1&a=2`), as
  OpenAPI and FastAPI define them. `fetchBaseQuery` joined them with commas. The
  only existing caller affected is `GET /users/by-ids` (`useUsersByIdsQuery`,
  author names on seven screens), which documents repeated keys: with several
  authors it received one invalid id and fell back to bare uids.
- **Deleted:** `useTaskSseManager` and its tests. The per-task SSE endpoint stays
  for its remaining consumer (the admin self-test pipeline).

## Capabilities

### New Capabilities

- `task-progress-tracking`: how the frontend follows the tasks the user
  started until each reaches its outcome.

### Modified Capabilities

None. `document-import-experience` requirements still hold; this change only
replaces the transport underneath them.

## Impact

- `libs/fred-core/fred_core/tasks/{authz,service,store}.py`, both `GET /tasks`
  routes, the regenerated OpenAPI specs and generated frontend clients.
- Frontend `features/tasks/` (polling hook, store reducer, selectors),
  `MainLayout`, `dynamicBaseQuery`, the task card and state badge, the import
  panel status line, English and French strings.
- Contract: dated entry in `CONTROL-PLANE-PRODUCT-CONTRACT.md` for the new
  `GET /tasks` parameter.
- Additive API change; no data migration, no configuration change.
