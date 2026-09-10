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
import { RESERVED_PROMPT_TAGS, findReservedPromptTag, reservedTagInPromptField } from "./promptValidation";

describe("findReservedPromptTag", () => {
  it("lists the four system-prompt blocks in prompt order", () => {
    expect(RESERVED_PROMPT_TAGS).toEqual(["platform_instructions", "platform_prompt", "tools", "agent_instructions"]);
  });

  it("reports opening, closing and self-closing forms, any case, spaces tolerated", () => {
    expect(findReservedPromptTag("x <tools> y")).toBe("tools");
    expect(findReservedPromptTag("x </agent_instructions> y")).toBe("agent_instructions");
    expect(findReservedPromptTag("<platform_prompt/>")).toBe("platform_prompt");
    expect(findReservedPromptTag("< /PLATFORM_INSTRUCTIONS >")).toBe("platform_instructions");
  });

  it("reports a tag carrying attributes, like the backend", () => {
    expect(findReservedPromptTag('<platform_instructions role="x">')).toBe("platform_instructions");
    expect(findReservedPromptTag("</agent_instructions x>")).toBe("agent_instructions");
  });

  it("reports the first one found", () => {
    expect(findReservedPromptTag("<example></platform_prompt><tools>")).toBe("platform_prompt");
  });

  it("accepts every other tag and the bare words", () => {
    expect(findReservedPromptTag("<example>…</example> <rules/> <br>")).toBeNull();
    expect(findReservedPromptTag("use the tools you are given")).toBeNull();
    expect(findReservedPromptTag("<tools_extra> <my_tools>")).toBeNull();
    expect(findReservedPromptTag("")).toBeNull();
  });
});

describe("reservedTagInPromptField", () => {
  it("looks at every string-valued field holding a string", () => {
    expect(reservedTagInPromptField({ type: "prompt" }, "x </agent_instructions>")).toBe("agent_instructions");
    expect(reservedTagInPromptField({ type: "string" }, "</tools>")).toBe("tools");
    expect(reservedTagInPromptField({ type: "prompt" }, "<example/>")).toBeNull();
    expect(reservedTagInPromptField({ type: "boolean" }, "</tools>")).toBeNull();
    expect(reservedTagInPromptField({ type: "prompt" }, undefined)).toBeNull();
  });
});
