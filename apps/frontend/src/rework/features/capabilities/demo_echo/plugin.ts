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

// The demo capability's UI plugin (AGENT-CAPABILITY-RFC §9) — one object,
// registered once in ../index.ts. It mirrors the backend `demo_echo`
// capability, whose manifest declares the `demo_card` chat part (#1977).

import type { CapabilityUiPlugin } from "../types";
import { DemoCardPartRenderer } from "./DemoCardPartRenderer";
import { DemoNotesPanel } from "./DemoNotesPanel";

export const demoEchoCapability: CapabilityUiPlugin = {
  id: "demo_echo",
  partRenderers: { demo_card: DemoCardPartRenderer },
  // Side panel keyed by the backend manifest's SidePanelSpec.widget (#1979).
  sidePanels: { demo_notes: DemoNotesPanel },
};
