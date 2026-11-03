## Context

The existing tab registry owns running, waiting and unread session state. Its unread marker currently treats every detached settlement as an answer, including failures. Sidebar rendering already subscribes to that registry.

## Goals / Non-Goals

Goals: readable waiting status, a plain blue completed-unread marker, and distinct running/failed states in the same PR, as explicitly requested.

Non-goals: server-backed status, cross-tab recovery, new notifications, runtime/API changes or a new shared component API.

## Decisions

Reuse the existing awaiting-input and unread sets. Track receipt of the authoritative final SSE event on the live turn; only a normal completed answer or user-input pause marks a detached conversation unread and notifies its owner. Errors and interrupted EOF do not imply an answer is ready.

Render the noninteractive waiting chip below metadata, using info-container/on-info-container tokens, compact emphasized text and no shadow. Keep running dots; use a single info-colored dot only for completed unread rows. Opening clears unread but keeps a pending question's chip until the next turn. Read-only deleted-agent rows do not solicit a reply.

## Risks / Trade-offs

Status is local to the tab. Mirror only the waiting and unread session-id sets in sessionStorage, up to the latest 100 ids per indicator, without message content or live-turn data. Restore once on module load and persist on indicator transitions, not queue updates or streamed chunks. Storage failure falls back to memory. History loading reconciles waiting; opening clears unread, starting a new turn clears waiting, and Stop/deletion clears both. No restore-time notification, extra history requests or server status API. Preserve queue cleanup and existing HITL semantics. Validate long labels, both locales, narrow sidebar geometry, keyboard navigation and a real final event rather than only synthetic registry state.
