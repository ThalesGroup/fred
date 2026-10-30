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

import { KeyCloakService } from "../../../security/KeycloakService";

declare const capturedCredential: unique symbol;

/**
 * The signed-in session's access token, captured for one turn.
 *
 * Branded so a turn cannot be pinned to an arbitrary string: the only way to
 * obtain one is `captureSessionCredential`, which reads the live session.
 */
export type CapturedCredential = string & { readonly [capturedCredential]: true };

export interface CapturedSession {
  credential: CapturedCredential;
  /** Life left on the captured credential when it was taken. */
  secondsLeft: number;
}

/** Capture the session's credential with its remaining life, or null when the
 *  session has no token or no usable expiry to measure against. */
export function captureSessionCredential(): CapturedSession | null {
  const token = KeyCloakService.GetToken();
  const secondsLeft = KeyCloakService.GetTokenSecondsLeft();
  if (!token || secondsLeft === null || !Number.isFinite(secondsLeft) || secondsLeft <= 0) return null;
  return { credential: token as CapturedCredential, secondsLeft };
}
