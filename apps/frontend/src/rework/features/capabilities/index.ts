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

// THE capability plugin index (AGENT-CAPABILITY-RFC §9) — the single shared
// edit when a capability ships UI: add its folder under
// `features/capabilities/<id>/` and its plugin object to this list. Every host
// slot (part renderers, form widgets, composer controls, side panels) resolves
// against this one index.

import type { CapabilityUiPlugin } from "./types";
import { demoEchoCapability } from "./demo_echo/plugin";
import { writableDocumentCapability } from "./writable_document/plugin";
import { pptFillerCapability } from "./ppt_filler/plugin";

export const capabilityUiPlugins: readonly CapabilityUiPlugin[] = [
  demoEchoCapability,
  writableDocumentCapability,
  pptFillerCapability,
];

export type { CapabilityUiPlugin, UiPartRenderer, UiPartRendererProps } from "./types";
