// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Which patch-note editions the current user closed without "Don't show again"
// during the current sign-in. Keyed by user and login session (the token's `sid`
// or `session_state`), so every tab of one sign-in shares it; rationale in D8.

import { KeyCloakService } from "../../../security/KeycloakService";

const KEY_PREFIX = "fred.patchNote.closed.";

/** A patch note edition: a re-shown note has a new `content_version`. */
export interface PatchNoteEdition {
  id: string;
  content_version: number;
}

interface Scope {
  storage: () => Storage;
  key: string;
  /** Prefix of this user's flags from other login sessions, pruned on write. */
  userPrefix?: string;
  sessionPrefix?: string;
}

function loginSessionId(): string | null {
  try {
    const claims = KeyCloakService.GetTokenParsed() as Record<string, unknown> | null;
    const sid = claims?.sid ?? claims?.session_state;
    return typeof sid === "string" && sid ? sid : null;
  } catch {
    return null;
  }
}

// Without a login-session id, fall back to the tab's sessionStorage.
function scope(note: PatchNoteEdition): Scope {
  const noteId = `${note.id}.v${note.content_version}`;
  const userPrefix = `${KEY_PREFIX}${KeyCloakService.GetUserId() ?? "unknown"}.`;
  const sid = loginSessionId();
  if (!sid) return { storage: () => window.sessionStorage, key: `${userPrefix}${noteId}` };
  const sessionPrefix = `${userPrefix}${sid}.`;
  return { storage: () => window.localStorage, key: `${sessionPrefix}${noteId}`, userPrefix, sessionPrefix };
}

export function wasClosedThisSession(note: PatchNoteEdition): boolean {
  try {
    const { storage, key } = scope(note);
    return storage().getItem(key) !== null;
  } catch {
    return false;
  }
}

export function markClosedThisSession(note: PatchNoteEdition): void {
  try {
    const { storage, key, userPrefix, sessionPrefix } = scope(note);
    const store = storage();
    if (userPrefix && sessionPrefix) {
      // Drop this user's flags from earlier sign-ins: at most one sign-in's worth stays.
      const stale: string[] = [];
      for (let i = 0; i < store.length; i++) {
        const k = store.key(i);
        if (k?.startsWith(userPrefix) && !k.startsWith(sessionPrefix)) stale.push(k);
      }
      stale.forEach((k) => store.removeItem(k));
    }
    store.setItem(key, "1");
  } catch {
    // Storage unavailable: the gate still keeps the dialog closed for this page view.
  }
}
