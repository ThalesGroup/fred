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
import { capabilityPreparingKey } from "./capabilityPreparing.ts";

const declared = new Set(["capability.ppt_builder.preparing", "capability.other.preparing"]);
const exists = (key: string) => declared.has(key);

describe("capabilityPreparingKey", () => {
  it("returns the one declaring capability's key", () => {
    expect(capabilityPreparingKey({ capability_config: { ppt_builder: {}, web: {} } }, exists)).toBe(
      "capability.ppt_builder.preparing",
    );
  });

  it("ignores a stored slice that is no longer selected", () => {
    const instance = { capability_config: { ppt_builder: {}, other: {} }, selected_capability_ids: ["other"] };
    expect(capabilityPreparingKey(instance, exists)).toBe("capability.other.preparing");
  });

  it("returns nothing when it cannot tell which capability is preparing", () => {
    expect(capabilityPreparingKey({ capability_config: { ppt_builder: {}, other: {} } }, exists)).toBeUndefined();
    expect(capabilityPreparingKey({ capability_config: { web: {} } }, exists)).toBeUndefined();
    expect(capabilityPreparingKey({}, exists)).toBeUndefined();
  });
});
