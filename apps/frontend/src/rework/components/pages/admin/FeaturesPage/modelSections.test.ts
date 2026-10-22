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

import { describe, expect, it } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { splitModelSections } from "./modelSections";

const model = (id: string, source: string | null): CapabilityEnablementItem =>
  ({ id, model_discovery_source_id: source }) as CapabilityEnablementItem;

describe("splitModelSections", () => {
  it("uses catalog provenance even when model ids resemble the other section", () => {
    const manual = model("model__openai__discovered.gateway.abc", null);
    const discovered = model("model__openai__chat", "gateway");

    expect(splitModelSections([manual, discovered])).toEqual({
      manual: [manual],
      discovered: [discovered],
    });
  });
});
