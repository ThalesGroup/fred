// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { expect, it } from "vitest";
import { readFileSync } from "node:fs";

it("agent form has no legacy model, author, or creation-assistant request hooks", () => {
  for (const file of ["AgentFormModal.tsx", "AgentFormBody.tsx"]) {
    expect(readFileSync(new URL(file, import.meta.url), "utf8")).not.toContain("legacyControlPlane");
  }
});
