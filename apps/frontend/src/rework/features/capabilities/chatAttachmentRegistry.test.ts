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

// Chat-attachment handler registry:
// a session's active capabilities resolve to the handlers their plugins declare.

import { describe, expect, it } from "vitest";
import { buildChatAttachmentRegistry, chatAttachmentHandlersForCapabilities } from "./chatAttachmentRegistry";
import type { CapabilityUiPlugin } from "./types";

describe("chatAttachmentRegistry", () => {
  const handle = async () => {};
  const withHandler: CapabilityUiPlugin = { id: "doc_keeper", onChatAttachment: handle };
  const withoutHandler: CapabilityUiPlugin = { id: "ppt_filler", sidePanels: {} };

  it("resolves only active capabilities that declare a handler, in the order supplied", () => {
    const other: CapabilityUiPlugin = { id: "other", onChatAttachment: handle };
    const registry = buildChatAttachmentRegistry([withHandler, withoutHandler, other]);

    const entries = chatAttachmentHandlersForCapabilities(
      ["other", "ppt_filler", "not_installed", "doc_keeper"],
      registry,
    );

    expect(entries.map((e) => e.capabilityId)).toEqual(["other", "doc_keeper"]);
  });
});
