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

import { act } from "react";
import { createInstance } from "i18next";
import en from "../../../../../../locales/en/translation.json";
import fr from "../../../../../../locales/fr/translation.json";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatListItem } from "./ChatListItem";

const labels = createInstance();
const branding = vi.hoisted(() => ({ agentsNicknameSingular: "Agent" }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: labels.t.bind(labels) }),
}));
vi.mock("../../../../../../hooks/useFrontendProperties", () => ({ useFrontendProperties: () => branding }));
beforeAll(async () => {
  await labels.init({ resources: { en: { translation: en }, fr: { translation: fr } }, lng: "en" });
});
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("ChatListItem deleted agent presentation", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(async () => {
    branding.agentsNicknameSingular = "Agent";
    await labels.changeLanguage("en");
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });
  function show(deleted: boolean, name: string | null = "Preserved assistant") {
    act(() =>
      root.render(
        <MemoryRouter>
          <ChatListItem
            sessionId="saved"
            href="/conversation?session=saved"
            label="Conversation title"
            agentName={name ?? undefined}
            agentDeleted={deleted}
            dateLabel="07/10/26 - 15:00"
            onDelete={vi.fn()}
          />
        </MemoryRouter>,
      ),
    );
  }
  it("labels the preserved agent name and announces the status without changing navigation", () => {
    show(true);
    const link = container.querySelector("a")!;
    const name = container.querySelector('[data-agent-deleted="true"]')!;
    expect(name.textContent).toBe("Preserved assistant (deleted)");
    expect(link.getAttribute("href")).toBe("/conversation?session=saved");
    expect(link.textContent).toContain("Conversation title");
    expect(link.textContent).toContain("(deleted)");
    const statusId = link.getAttribute("aria-describedby")!.split(" ")[0];
    expect(document.getElementById(statusId)?.textContent).toBe("Agent deleted - read-only conversation");
  });
  it("shows the deletion explanation on keyboard focus and hover, including grouped entries", () => {
    show(true, null);
    const link = container.querySelector("a")!;
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
      link.focus();
    });
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe("Agent deleted - read-only conversation");
    act(() => link.blur());
    act(() => link.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe("Agent deleted - read-only conversation");
  });
  it.each([
    ["en", "(deleted)", " deleted - read-only conversation"],
    ["fr", "(supprimé)", " supprimé - conversation en lecture seule"],
  ])("localizes the %s suffix and keeps an empty configured nickname", async (language, suffix, status) => {
    branding.agentsNicknameSingular = "";
    await labels.changeLanguage(language);
    show(true);
    const link = container.querySelector("a")!;
    const statusId = link.getAttribute("aria-describedby")!.split(" ")[0];
    expect(document.getElementById(statusId)?.textContent).toBe(status);
    act(() => link.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe(`Preserved assistant - ${status}`);
    expect(container.querySelector("[data-agent-deleted]")?.textContent).toBe(`Preserved assistant ${suffix}`);
    expect(container.textContent).not.toContain("{{");
  });
  it("keeps live agent names and entries free of deletion status", () => {
    show(false);
    expect(container.querySelector('[data-agent-deleted="true"]')).toBeNull();
    expect(container.querySelector("a")?.getAttribute("aria-describedby")).toBeNull();
    expect(container.textContent).not.toContain("read-only");
    expect(container.textContent).not.toContain("(deleted)");
  });
});
