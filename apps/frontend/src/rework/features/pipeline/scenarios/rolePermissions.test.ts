// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
import { expect, it } from "vitest";
import { expectedTeamPermissions } from "./rolePermissions";
it("public discovery does not imply membership or content access", () => {
  expect(expectedTeamPermissions([], "private")).toEqual([]);
  expect(expectedTeamPermissions([], "public")).toEqual(["can_read"]);
});
it("pending administrators get membership without governance or content editing", () => {
  const p = expectedTeamPermissions(["pending_team_admin"], "private");
  expect(p).toContain("can_read_members");
  expect(p).not.toContain("can_administer_members");
  expect(p).not.toContain("can_update_resources");
});
it("team administrators govern but cannot edit prompts without editor", () => {
  const p = expectedTeamPermissions(["team_admin"], "private");
  expect(p).toContain("can_administer_members");
  expect(p).toContain("can_run_evaluations");
  expect(p).not.toContain("can_update_resources");
  expect(p).not.toContain("can_read_conversations_for_evaluation");
});
it("analysts evaluate without content editing or governance", () => {
  const p = expectedTeamPermissions(["team_analyst"], "private");
  expect(p).toContain("can_read_conversations_for_evaluation");
  expect(p).not.toContain("can_administer_members");
  expect(p).not.toContain("can_update_resources");
});
it("cumulative roles combine independent permissions without duplicates", () => {
  const p = expectedTeamPermissions(["team_admin", "team_editor", "team_analyst"], "private");
  expect(p).toContain("can_administer_members");
  expect(p).toContain("can_update_resources");
  expect(p).toContain("can_read_conversations_for_evaluation");
  expect(new Set(p).size).toBe(p.length);
});
