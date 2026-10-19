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

// Reuse an already-painted buffer when srcdoc is unchanged and no load event fires.

export type BufferIndex = 0 | 1;

export type BufferAction =
  | { kind: "none" }
  | { kind: "flip"; to: BufferIndex } // already painted elsewhere - reveal it, no reload
  | { kind: "load"; into: BufferIndex }; // fresh doc - load into the hidden back buffer

// Choose the buffer to reveal or load for the requested document.
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
  // Its srcDoc is already `composed` but it hasn't painted yet - it's mid-load;
  // the onLoad will flip to it. Don't reset the srcDoc (that would restart it).
  if (buffers[back] === composed) return { kind: "none" };
  return { kind: "load", into: back };
}
