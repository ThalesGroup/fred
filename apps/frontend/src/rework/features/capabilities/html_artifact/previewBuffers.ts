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

// Pure decision for the Preview's double-buffer (two stacked sandboxed iframes).
// The subtlety this encodes: an iframe only fires `onLoad` when its `srcDoc`
// actually changes, so switching BACK to a document a buffer already painted
// produces no reload and no onLoad. The consumer must then flip to that buffer
// directly — otherwise the pane freezes on the current frame (the switch-tab bug).

export type BufferIndex = 0 | 1;

export type BufferAction =
  | { kind: "none" }
  | { kind: "flip"; to: BufferIndex } // already painted elsewhere — reveal it, no reload
  | { kind: "load"; into: BufferIndex }; // fresh doc — load into the hidden back buffer

/**
 * Decide what to do when `composed` is the document that should now be shown.
 * `buffers` is each frame's current `srcDoc`; `painted` is what each frame has
 * actually finished painting (from onLoad); `front` is the visible frame.
 */
export function nextBufferAction(
  composed: string,
  buffers: readonly [string, string],
  painted: readonly [string, string],
  front: BufferIndex,
): BufferAction {
  if (!composed || buffers[front] === composed) return { kind: "none" };
  const back: BufferIndex = front === 0 ? 1 : 0;
  // Already painted in the back buffer on an earlier view: no reload will fire,
  // so flip to it now rather than waiting for an onLoad that never comes.
  if (painted[back] === composed) return { kind: "flip", to: back };
  // Its srcDoc is already `composed` but it hasn't painted yet — it's mid-load;
  // the onLoad will flip to it. Don't reset the srcDoc (that would restart it).
  if (buffers[back] === composed) return { kind: "none" };
  return { kind: "load", into: back };
}
