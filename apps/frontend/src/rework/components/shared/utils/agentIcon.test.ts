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
import { guessAgentIcon } from "./agentIcon";

describe("guessAgentIcon", () => {
  it("matches a keyword in the role when the name and description are unhelpful", () => {
    expect(guessAgentIcon("Aegis", "Reviews contracts for legal compliance", "", "smart_toy")).toBe("gavel");
  });

  it("matches a keyword in the description when the name and role are unhelpful", () => {
    expect(guessAgentIcon("Aegis", "", "Handles customer support tickets", "smart_toy")).toBe("support_agent");
  });

  it("matches French keywords, not just English ones", () => {
    expect(guessAgentIcon("Sentinelle", "Surveille la sécurité des systèmes", "", "smart_toy")).toBe("shield");
  });

  it("prefers the first matching rule when multiple keywords are present", () => {
    // "legal" (gavel) is listed before "code" (code) in the rule order.
    expect(guessAgentIcon("Multi", "Reviews legal contracts for our codebase", "", "smart_toy")).toBe("gavel");
  });

  it("falls back to the provided default when nothing matches", () => {
    expect(guessAgentIcon("Blorp", "Does a thing", "Nothing keyword-worthy here", "widgets")).toBe("widgets");
  });

  it("is case-insensitive", () => {
    expect(guessAgentIcon("TRANSLATOR", "TRANSLATES DOCUMENTS", "", "smart_toy")).toBe("translate");
  });
});
