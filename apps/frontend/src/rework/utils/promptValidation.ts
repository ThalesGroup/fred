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

// Mirror of RESERVED_PROMPT_TAGS / find_reserved_prompt_tag in fred-sdk
// contracts/prompt_utils.py, so an author sees the refusal while typing. The
// backend is the reference and still refuses (422) whatever slips past here.
export const RESERVED_PROMPT_TAGS = [
  "platform_instructions",
  "platform_prompt",
  "tools",
  "agent_instructions",
] as const;

const RESERVED_TAG_RE = new RegExp(`<\\s*/?\\s*(${RESERVED_PROMPT_TAGS.join("|")})(?=[\\s/>])[^>]*>`, "i");

// Every string-valued tuning field is substituted into the agent template by
// the runtime, so the backend refuses a reserved tag in all of them.
const STRING_FIELD_TYPES = new Set(["string", "text", "text-multiline", "prompt"]);

/** Name of the first reserved tag written as an XML tag in `text`, else null. */
export function findReservedPromptTag(text: string): string | null {
  const match = RESERVED_TAG_RE.exec(text);
  return match ? match[1].toLowerCase() : null;
}

/** The reserved tag a string-valued tuning field currently holds, else null. */
export function reservedTagInPromptField(field: { type?: string | null }, value: unknown): string | null {
  return field.type && STRING_FIELD_TYPES.has(field.type) && typeof value === "string"
    ? findReservedPromptTag(value)
    : null;
}
