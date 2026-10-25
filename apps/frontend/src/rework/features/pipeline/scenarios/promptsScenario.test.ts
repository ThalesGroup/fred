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
import { collect, FakePlatform, signal } from "./fakePlatform";
import { promptsScenario } from "./promptsScenario";

async function run(platform: FakePlatform, deps = platform.promptsDeps()) {
  const r = collect();
  await promptsScenario(deps, r.report, signal);
  return r;
}

describe("promptsScenario", () => {
  it("passes every check and removes session, prompt, category and agent", async () => {
    const platform = new FakePlatform();
    const r = await run(platform);
    expect(r.steps.filter((s) => s.status !== "passed").map((s) => `${s.id}:${s.status}`)).toEqual([]);
    expect([platform.sessions.size, platform.prompts.size, platform.categories.size, platform.agents.size]).toEqual([
      0, 0, 0, 0,
    ]);
  });

  it("fails when the session drops the attached prompt", async () => {
    const platform = new FakePlatform();
    const deps = platform.promptsDeps();
    deps.attachSessionPrompts = async () => {};
    expect((await run(platform, deps)).status("query-context-prompt")).toBe("failed");
  });

  it("cleans a category and prompt after their post-create checks fail", async () => {
    const platform = new FakePlatform();
    const deps = platform.promptsDeps();
    deps.listCategories = async () => [];
    deps.readPrompt = async () => {
      throw new Error("read failed");
    };
    const r = await run(platform, deps);
    expect(r.status("create-category")).toBe("failed");
    expect(r.status("create-prompt")).toBe("failed");
    expect(platform.categories.size).toBe(0);
    expect(platform.prompts.size).toBe(0);
  });

  it("fails when an edit does not reach the session", async () => {
    const platform = new FakePlatform();
    const deps = platform.promptsDeps();
    deps.updatePrompt = async () => {};
    expect((await run(platform, deps)).status("prompt-update")).toBe("failed");
  });

  it("fails when the command is not offered, or a favorite cannot be removed", async () => {
    const platform = new FakePlatform();
    const deps = platform.promptsDeps();
    deps.listCommands = async () => [];
    const favorites = deps.setFavorite;
    deps.setFavorite = async (id, favorite) => {
      if (favorite) await favorites(id, true);
    };
    const r = await run(platform, deps);
    expect(r.status("prompt-command")).toBe("failed");
    expect(r.status("favorite")).toBe("failed");
  });

  it("fails when a deleted prompt can still be read", async () => {
    const platform = new FakePlatform();
    const deps = platform.promptsDeps();
    deps.deleteContextPrompt = async () => {};
    const r = await run(platform, deps);
    expect(r.status("prompt-gone")).toBe("failed");
  });
});
