# RFC: Chat Composer State Hardening (CHAT-07)

**Status:** Implemented (2026-05-24)  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-24  
**ID:** CHAT-07  
**Backlog:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §8`  
**Contract impact:** `CONTROL-PLANE-PRODUCT-CONTRACT.md` — `ManagedAgentInstanceSummary` extended

---

## 1. Problem

The chat composer (`RichInputField` + `ComposerSettingsControls`) suffers from five
connected state-management defects identified during CHAT-03/CHAT-05 delivery:

### 1.1 Agent capabilities arrive too late

`effectiveChatOptions` is set as a side-effect of `send()` → `prepareExecution`.
On every fresh page load and every session switch the value is `null` until the
user sends a message.  Consequence: composer controls either do not appear
(opt-in logic, current after bugfix) or appear incorrectly (pre-bugfix opt-out
logic).  An agent with KF search tools shows no controls until the first message.

### 1.2 Composer defaults reset to hardcoded values

`searchPolicy` and `ragScope` are initialized to `"hybrid"` / `"hybrid"` in
`useState`.  They are overwritten by `effectiveChatOptions` only after the first
`send()`.  Switching sessions resets them to the hardcoded constants, not to the
agent-configured defaults (`default_search_policy`, `default_search_rag_scope`).

### 1.3 Per-session composer choices lost on navigation

Library selection, search policy, and RAG scope the user set in session X are
pure React state — lost the moment they navigate away.  Returning to that session
shows defaults, not the user's last choices.

### 1.4 `reset()` does not cancel in-flight streaming

`useChatSse.reset()` clears messages but leaves the `AbortController` running.
The old SSE stream continues delivering events to `messagesRef` after the reset;
`waitResponse` stays `true` until the stream ends.  Switching sessions while
streaming leaves the UI in a half-streaming state.

### 1.5 `useChatSse` state leaks across agent navigation

React re-renders `ManagedChatPage` with new `useParams` values when navigating
between agents; it does not remount the component.  All hook state persists
across the agent change until `reset()` runs reactively.  The fix added in the
current bugfix cycle (add `agentInstanceId` to the reset effect deps) mitigates
this, but is fragile — if the route changes cause a different remount pattern,
the mitigation silently disappears.

---

## 2. Proposed solution

Five targeted changes in dependency order.  No new layers, no new abstractions
beyond a single extracted hook.

### Step 1 — `reset()` calls `abort()` (trivial)

`useChatSse.reset()` calls `abort()` before clearing messages.  This cancels any
in-flight SSE fetch atomically with the state clear.

```
reset() {
  this.abort()          // cancel SSE, set waitResponse=false
  clearMessages()       // clear messages + effectiveChatOptions
}
```

**Files:** `useChatSse.ts` — 1 line.

### Step 2 — `key={agentInstanceId}` on the page route (trivial)

React guarantees a full component remount when the `key` prop changes.  Adding
`key={agentInstanceId}` at the route definition level ensures a clean hook slate
whenever the agent changes, regardless of future routing refactors.

```tsx
<Route path="..." element={<ManagedChatPage key={agentInstanceId} />} />
```

The `agentInstanceId` dep in the `useManagedChat` reset effect can then be
removed — it becomes redundant.

**Files:** The router file that renders `ManagedChatPage` — 1 prop addition.

### Step 3 — Add `effective_chat_options` to `ManagedAgentInstanceSummary`

The control plane already computes `effective_chat_options` in
`_resolve_effective_chat_options()`.  It is only exposed today via
`ExecutionPreparation`.  This step adds it as a read-only field on the instance
summary returned by `GET/POST/PATCH /teams/{team_id}/agent-instances`.

```python
class ManagedAgentInstanceSummary(BaseModel):
    ...
    effective_chat_options: EffectiveChatOptions  # NEW — computed at read time
```

The field is computed, never stored.  No migration needed.  The frontend already
fetches the instance list at mount via
`useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery`.

**Contract change:** `CONTROL-PLANE-PRODUCT-CONTRACT.md §3.2
ManagedAgentInstanceSummary` — add `effective_chat_options` field.

**Files:** `product/service.py` (`_record_to_summary`), OpenAPI regeneration,
`controlPlaneOpenApi.ts` (regenerated — do not hand-edit).

### Step 4 — Initialize composer defaults from agent summary at mount

`useManagedChat` reads `effectiveChatOptions` from the instance summary (Step 3)
instead of waiting for `prepareExecution`.  The SSE hook still receives the value
from `prepareExecution` and can override it (e.g. when runtime resolves a
context-prompt that changes defaults), but the summary value is the stable
baseline.

`searchPolicy` and `ragScope` are initialized via `useMemo` from the agent
summary, not hardcoded constants:

```ts
const agentDefaults = agentInstances?.find(i => i.agent_instance_id === agentInstanceId);
const defaultPolicy = agentDefaults?.effective_chat_options?.default_search_policy ?? "hybrid";
const defaultScope  = agentDefaults?.effective_chat_options?.default_search_rag_scope ?? "hybrid";
```

**Files:** `useManagedChat.ts` — read path changed, no new hook yet.

### Step 5 — `useComposerSettings` with `sessionStorage` persistence

Extract a `useComposerSettings(sessionId, agentDefaults)` hook that:

- Initialises `searchPolicy`, `ragScope`, `selectedLibraryIds` from `sessionStorage`
  key `chat.composer.{sessionId}` if present, otherwise from `agentDefaults`.
- Writes to `sessionStorage` on every change.
- Clears the key when the session is explicitly deleted (future: on session
  `DELETE` call).

`sessionStorage` survives navigation within a tab but not browser close —
the right tradeoff for ephemeral chat-session state.

```ts
const STORAGE_KEY = (sid: string) => `chat.composer.${sid}`;

function useComposerSettings(sessionId: string | null, defaults: ComposerDefaults) {
  const stored = sessionId ? sessionStorage.getItem(STORAGE_KEY(sessionId)) : null;
  const initial = stored ? JSON.parse(stored) : defaults;
  const [policy, setPolicy] = useState(initial.searchPolicy);
  const [scope,  setScope]  = useState(initial.ragScope);
  const [libs,   setLibs]   = useState(initial.selectedLibraryIds);
  // write-through on every setter
  ...
}
```

`useManagedChat` delegates to this hook instead of owning the three state vars
directly.

**Files:** new `useComposerSettings.ts` in `pages/ManagedChatPage/`, updated
`useManagedChat.ts`.

---

## 3. Alternatives considered

| Alternative | Reason rejected |
|---|---|
| Store composer settings in the session DB record | Adds a backend write on every chip click; session record is for agent-authored metadata, not transient user preferences |
| `localStorage` instead of `sessionStorage` | Survives browser close → risk of stale library selections leaking across sessions days later |
| Single `useEffect` to sync defaults on `effectiveChatOptions` change | Current pattern — the bug we are fixing; reactive sync is always one render late |
| Add a `/capabilities` endpoint | Extra round-trip; the summary already makes the same server call |

---

## 4. Contract impact summary

| Contract file | Change |
|---|---|
| `CONTROL-PLANE-PRODUCT-CONTRACT.md §3.2` | Add `effective_chat_options: EffectiveChatOptions` (read-only, computed) to `ManagedAgentInstanceSummary` |
| `RUNTIME-EXECUTION-CONTRACT.md` | No change — `ExecutionPreparation.effective_chat_options` is kept and may still override the summary value |
| `controlPlaneOpenApi.ts` | Regenerated from source — do not hand-edit |

---

## 5. Implementation order and file map

| Step | Files | Risk |
|---|---|---|
| 1 — reset calls abort | `useChatSse.ts` | Trivial |
| 2 — key on route | router file (to be confirmed) | Trivial |
| 3 — summary field | `service.py`, OpenAPI regen | Low — additive only |
| 4 — defaults from summary | `useManagedChat.ts` | Low |
| 5 — `useComposerSettings` | new `useComposerSettings.ts`, `useManagedChat.ts` | Medium — state refactor |

Total scope: ~6 files, ~120 lines of meaningful change.  No design rules
violated: the change is additive on the backend contract, follows existing
hook patterns, and introduces one new hook of single responsibility.

Steps 1–2 are mechanical fixes with zero design risk and can be shipped
independently.  Steps 3–5 form a coherent unit that should not be split.
