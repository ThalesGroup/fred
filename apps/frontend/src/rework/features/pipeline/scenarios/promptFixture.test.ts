// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
import { expect, it, vi } from "vitest";
import { verifiedPromptIdForCommand, type AccountRequest } from "./promptFixture";
const base = "/control-plane/v1/teams/run-team/prompts";
function request(prompt: unknown, commandStatus = 200) {
  return vi.fn<AccountRequest>(async (path) =>
    path.endsWith("/prompt-commands")
      ? { status: commandStatus, body: [{ command: "run-command", prompt_id: "run-prompt" }] }
      : { status: 200, body: prompt },
  );
}
it("resolves the uncapped command catalog and exact run identity", async () => {
  const r = request({ id: "run-prompt", name: "run-name", text: "run-text" });
  expect(await verifiedPromptIdForCommand(r, base, "token", "run-command", "run-name", "run-text")).toBe("run-prompt");
  expect(r.mock.calls.map((call) => call[0])).toEqual([
    "/control-plane/v1/teams/run-team/prompt-commands",
    `${base}/run-prompt`,
  ]);
});
it.each([401, 403, 404, 429, 500])("does not treat HTTP %i as a missing fixture", async (status) => {
  await expect(
    verifiedPromptIdForCommand(request({}, status), base, "token", "run-command", "run-name", "run-text"),
  ).rejects.toThrow(`HTTP ${status}`);
});
it.each([
  { id: "existing", name: "run-name", text: "run-text" },
  { id: "run-prompt", name: "existing", text: "run-text" },
  { id: "run-prompt", name: "run-name", text: "existing" },
])("refuses a command collision or mismatched fixture %j", async (prompt) => {
  await expect(
    verifiedPromptIdForCommand(request(prompt), base, "token", "run-command", "run-name", "run-text"),
  ).rejects.toThrow("does not identify this run's prompt");
});
it("returns absence only after a successful command lookup", async () => {
  const r: AccountRequest = async () => ({ status: 200, body: [] });
  expect(await verifiedPromptIdForCommand(r, base, "token", "run-command", "run-name", "run-text")).toBeNull();
});
