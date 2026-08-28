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

// The open conversation's id, the scoping key for every piece of capability state.
//
// Capability slices are global while their content belongs to one conversation, so
// each of them stamps what it stores with the id these hooks return. One definition
// of the `?session=` read (and of the "no conversation open" value, `""`) beats the
// copy every renderer used to carry.

import { useRef } from "react";
import { useSearchParams } from "react-router-dom";

/** The conversation currently open, or `""` when there is none. */
export function useOpenSessionId(): string {
  const [searchParams] = useSearchParams();
  return searchParams.get("session") ?? "";
}

/**
 * The conversation a chat-part renderer was mounted for, or `""` once the user has
 * navigated away from it.
 *
 * Switching conversations re-renders the OUTGOING conversation's cards once (the
 * thread is cleared in a parent effect, which runs after theirs), so a card reading
 * the URL directly would stamp its part with the INCOMING conversation's id - and
 * light that capability's panel up on a chat that never produced anything.
 */
export function useMountSessionId(): string {
  const sessionId = useOpenSessionId();
  const mounted = useRef<string | null>(null);
  // Lazy init, idempotent - a card mounted before the id exists adopts the first one.
  if (mounted.current === null && sessionId !== "") mounted.current = sessionId;
  return mounted.current === sessionId ? sessionId : "";
}
