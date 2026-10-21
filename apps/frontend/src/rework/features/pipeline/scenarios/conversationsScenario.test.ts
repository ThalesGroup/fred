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
import { conversationsScenario } from "./conversationsScenario";
import { collect, FakePlatform, signal } from "./fakePlatform";

async function run(platform: FakePlatform, deps = platform.conversationsDeps()) {
  const r = collect();
  await conversationsScenario(deps, r.report, signal);
  return r;
}

describe("conversationsScenario", () => {
  it("passes every check and leaves no conversation, attachment or agent", async () => {
    const platform = new FakePlatform();
    const r = await run(platform);
    expect(r.steps.filter((s) => s.status !== "passed").map((s) => `${s.id}:${s.status}`)).toEqual([]);
    expect([platform.sessions.size, platform.attachments.size, platform.agents.size]).toEqual([0, 0, 0]);
  });

  it("skips the listing check when no conversation was created", async () => {
    const platform = new FakePlatform();
    platform.templates.clear();
    const r = await run(platform);
    expect(r.status("session-listed")).toBe("skipped");
  });

  it("fails when an attachment is visible from another conversation", async () => {
    const platform = new FakePlatform();
    const deps = platform.conversationsDeps();
    deps.searchSession = async () => [...platform.attachments].map(([uid, a]) => ({ uid, content: a.text }));
    expect((await run(platform, deps)).status("attachment-isolation")).toBe("failed");
  });

  it("fails when a rename is lost", async () => {
    const platform = new FakePlatform();
    const deps = platform.conversationsDeps();
    deps.renameSession = async () => {};
    expect((await run(platform, deps)).status("rename-session")).toBe("failed");
  });

  it("fails when a deleted attachment stays retrievable", async () => {
    const platform = new FakePlatform();
    const deps = platform.conversationsDeps();
    const search = deps.searchSession;
    const kept: Array<{ uid: string; content: string }> = [];
    deps.searchSession = async (sessionId, question) => {
      const hits = await search(sessionId, question);
      if (hits.length) kept.splice(0, kept.length, ...hits);
      return hits.length || sessionId !== [...platform.sessions.keys()][0] ? hits : kept;
    };
    expect((await run(platform, deps)).status("delete-attachment")).toBe("failed");
  });

  it("deletes what bulk deletion left behind", async () => {
    const platform = new FakePlatform();
    const deps = platform.conversationsDeps();
    const bulk = deps.bulkDelete;
    deps.bulkDelete = async (ids) => bulk(ids.slice(0, 1));
    const r = await run(platform, deps);
    expect(r.status("bulk-delete")).toBe("failed");
    expect(platform.sessions.size).toBe(0);
  });

  it("deletes the conversations one by one when bulk deletion never ran", async () => {
    const platform = new FakePlatform();
    const deps = platform.conversationsDeps();
    deps.attach = async () => {
      throw new Error("upload refused");
    };
    deps.bulkDelete = async () => {
      throw new Error("bulk deletion unavailable");
    };
    const r = await run(platform, deps);
    expect(r.status("attach-file")).toBe("failed");
    expect(platform.sessions.size).toBe(0);
  });

  it("deletes an attachment when its listing check fails", async () => {
    const platform = new FakePlatform();
    const deps = platform.conversationsDeps();
    deps.listAttachments = async () => [];
    const r = await run(platform, deps);
    expect(r.status("attach-file")).toBe("failed");
    expect([r.status("delete-attachment"), r.status("cleanup-attachment")]).toContain("passed");
    expect(platform.attachments.size).toBe(0);
  });
});
