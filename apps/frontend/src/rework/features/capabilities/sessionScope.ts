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

// Capability session scope signal.
//
// Why this exists:
// - capability slices hold per-conversation UI state (e.g. the ppt_filler
//   preview currently shown, its once-per-view auto-open guard). That state
//   must reset when the chat page mounts on / switches to another session,
//   or one conversation's panel content leaks into the next
// - the chat page is the only component that knows the active session id, but
//   it must stay capability-agnostic — so it dispatches this single generic
//   action and each capability slice resets itself via `extraReducers`
//
// The payload is the new session id (null while a fresh conversation is not
// yet bound). Listeners should treat EVERY dispatch as a scope reset: the
// page also fires it on mount, so returning to the same conversation counts
// as a fresh view (auto-open behaviors re-arm, mirroring Kea's per-view refs).

import { createAction } from "@reduxjs/toolkit";

export const chatSessionScopeChanged = createAction<string | null>("capabilities/chatSessionScopeChanged");
