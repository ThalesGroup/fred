// @vitest-environment happy-dom
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

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { CommandMenu, type CommandMenuEmptyReason, type CommandMenuEntry } from "./CommandMenu";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) => (options?.name ? `${key}:${options.name}` : key),
  }),
}));

const prompt = (source: "team" | "personal", command: string): CommandMenuEntry => ({
  kind: "prompt",
  source,
  promptId: `${source}-${command}`,
  promptTeamId: source,
  command,
  name: command,
});
const skill = (name: string): CommandMenuEntry => ({
  kind: "skill",
  source: "platform",
  promptId: `platform:skill:${name}`,
  command: name,
  name,
});

function render(
  entries: CommandMenuEntry[],
  props: { activeIndex?: number; teamName?: string; empty?: CommandMenuEmptyReason } = {},
) {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(
    <CommandMenu
      id="menu"
      entries={entries}
      activeIndex={props.activeIndex ?? 0}
      empty={props.empty ?? "noMatch"}
      teamName={props.teamName}
      optionId={(index) => `option-${index}`}
      onActivate={() => {}}
      onFocusEntry={() => {}}
    />,
  );
  const groups = Array.from(host.querySelectorAll<HTMLElement>('[role="group"]'));
  const heading = (group: HTMLElement) =>
    host.querySelector<HTMLElement>(`[id="${group.getAttribute("aria-labelledby")}"]`);
  return {
    host,
    headings: groups.map((group) => heading(group)),
    sections: groups.map((group) => [
      heading(group)?.textContent,
      Array.from(group.querySelectorAll('[role="option"]')).map((option) => option.id),
    ]),
  };
}

const ALL = [prompt("team", "search"), prompt("team", "summary"), prompt("personal", "summary"), skill("review")];

describe("CommandMenu sections", () => {
  it("lists team, personal space and platform skills in that order, each under its heading", () => {
    const { host, sections } = render(ALL, { teamName: "Finance" });
    expect(sections).toEqual([
      ["chatbot.commandMenu.sections.team:Finance", ["option-0", "option-1"]],
      ["chatbot.commandMenu.sections.personal", ["option-2"]],
      ["chatbot.commandMenu.sections.platform", ["option-3"]],
    ]);
    expect(host.querySelector('[role="listbox"]')?.children).toHaveLength(3);
  });

  it("hides a section that has no entry, together with its heading", () => {
    const { host, sections } = render([prompt("personal", "summary")], { teamName: "Finance" });
    expect(sections).toEqual([["chatbot.commandMenu.sections.personal", ["option-0"]]]);
    expect(host.textContent).not.toContain("chatbot.commandMenu.sections.team");
    expect(host.textContent).not.toContain("chatbot.commandMenu.sections.platform");
  });

  it("names the team section without a name until the team is known", () => {
    expect(render([prompt("team", "search")]).sections[0][0]).toBe("chatbot.commandMenu.sections.teamFallback");
  });

  it("labels each group by its own heading and repeats the full label as a tooltip", () => {
    const { headings } = render(ALL, { teamName: "A very long team name" });
    expect(new Set(headings.map((heading) => heading?.id)).size).toBe(3);
    expect(headings[0]?.title).toBe("chatbot.commandMenu.sections.team:A very long team name");
  });

  it("keeps one focus and the flat option index across sections", () => {
    const { host } = render(ALL, { activeIndex: 2 });
    const selected = Array.from(host.querySelectorAll('[role="option"][aria-selected="true"]'));
    expect(selected.map((option) => option.id)).toEqual(["option-2"]);
    expect(selected[0].closest('[role="group"]')?.getAttribute("data-source")).toBe("personal");
  });

  it.each(["loading", "none", "noMatch"] as const)("shows the %s line as a status when it has no row", (empty) => {
    const { host } = render([], { empty });
    expect(host.querySelector('[role="status"]')?.textContent).toBe(`chatbot.commandMenu.${empty}`);
    expect(host.querySelector('[role="listbox"]')).toBeNull();
  });

  it("shows its rows rather than a status line whatever the empty reason", () => {
    const { host } = render(ALL, { empty: "loading" });
    expect(host.querySelector('[role="status"]')).toBeNull();
    expect(host.querySelectorAll('[role="option"]')).toHaveLength(4);
  });

  it("shows no source label on a row", () => {
    const { host } = render(ALL);
    expect(host.textContent).not.toContain("chatbot.commandMenu.sources.");
    expect(host.querySelector('[role="option"]')?.textContent).toBe("edit_note/searchsearch");
  });
});
