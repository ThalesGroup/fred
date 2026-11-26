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

// The `memory` capability's UI half: a small chat card for each note the agent
// remembers or forgets, and the note's text on the approval card shown when a
// note follows content the agent read. Editors manage the notes in the agent
// form's Memory section.

import type { CapabilityUiPlugin } from "../types";
import { CAPABILITY_ID } from "./types";
import { MemoryNoteCard } from "./MemoryNoteCard";
import { MemoryRememberReview } from "./MemoryRememberReview";

export const memoryCapability: CapabilityUiPlugin = {
  id: CAPABILITY_ID,
  partRenderers: { memory_note: MemoryNoteCard },
  hitlRenderers: { memory_remember: MemoryRememberReview },
};
