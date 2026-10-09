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
import type { AvailableModelProfile } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { rowForProfile, teamModelRows } from "./teamModelRows";

const GPT = "model__openai__gpt-5";
const PROFILES: AvailableModelProfile[] = [
  { profile_id: "chat.gpt5", capability_id: GPT, name: "gpt-5", display_name: "GPT-5" },
  { profile_id: "chat.gpt5.alt", capability_id: GPT, name: "gpt-5", display_name: "GPT-5" },
];

describe("teamModelRows", () => {
  it("keys a two-profile model by the first preferred profile it owns, whatever the order", () => {
    expect(teamModelRows(PROFILES, ["chat.gpt5.alt", "chat.gpt5"]).map((row) => row.profileId)).toEqual([
      "chat.gpt5.alt",
    ]);
    expect(teamModelRows(PROFILES, ["chat.gpt5", "chat.gpt5.alt"]).map((row) => row.profileId)).toEqual(["chat.gpt5"]);
    expect(teamModelRows(PROFILES).map((row) => row.profileId)).toEqual(["chat.gpt5"]);
  });

  it("finds a model's row from any of its profiles", () => {
    const rows = teamModelRows(PROFILES, ["chat.gpt5.alt"]);
    expect(rowForProfile(rows, PROFILES, "chat.gpt5")?.profileId).toBe("chat.gpt5.alt");
    expect(rowForProfile(rows, PROFILES, "chat.unknown")).toBeUndefined();
  });
});
