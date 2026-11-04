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
import {
  abortTurn,
  markSessionRead,
  registerTurn,
  setSessionAwaitingInput,
  settleTurn,
  subscribeBackgroundSettled,
  type LiveTurn,
} from "@core/hooks/backgroundTurns";

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
    act(() => abortTurn("saved"));
    act(() => root.unmount());
    container.remove();
  });
  function show(deleted: boolean, name: string | null = "Preserved assistant", tooltipName?: string) {
    act(() =>
      root.render(
        <MemoryRouter>
          <ChatListItem
            sessionId="saved"
            href="/conversation?session=saved"
            label="Conversation title"
            agentName={name ?? undefined}
            agentTooltipName={tooltipName}
            agentDeleted={deleted}
            dateLabel="07/10/26 - 15:00"
            onDelete={vi.fn()}
          />
        </MemoryRouter>,
      ),
    );
  }
  it("shows animated dots and announces the answer while its turn streams, until it ends", () => {
    show(false);
    expect(container.textContent).not.toContain("Answer in progress");
    const turn: LiveTurn = {
      sessionId: "saved",
      controller: new AbortController(),
      steeringTurnId: "steering",
      thoughts: new Map(),
      host: null,
      messages: [],
      scope: { actor: "test-login", spaceId: "space-1", agentInstanceId: "agent-1" },
      detachedCallbacks: {},
    };
    act(() => registerTurn(turn));
    expect(container.querySelector("a")!.textContent).toContain("Answer in progress");
    act(() => settleTurn(turn));
    expect(container.textContent).not.toContain("Answer in progress");
  });
  it("shows the waiting chip after a question, including after opening, until the next turn or deletion", () => {
    show(false);
    const turnOn = (awaitingInput: boolean): LiveTurn => ({
      sessionId: "saved",
      controller: new AbortController(),
      steeringTurnId: "steering",
      thoughts: new Map(),
      host: null,
      messages: [],
      scope: { actor: "test-login", spaceId: "space-1", agentInstanceId: "agent-1" },
      detachedCallbacks: {},
      awaitingInput,
    });
    const question = turnOn(true);
    act(() => registerTurn(question));
    act(() => settleTurn(question));
    expect(container.querySelector('[class*="awaitingInput"]')?.textContent).toBe("Awaiting reply");
    act(() => markSessionRead("saved"));
    expect(container.textContent).toContain("Awaiting reply");
    expect(container.textContent).not.toContain("Answer in progress");

    const answer = turnOn(false);
    act(() => registerTurn(answer));
    expect(container.textContent).toContain("Answer in progress");
    expect(container.textContent).not.toContain("Awaiting reply");
    act(() => settleTurn(answer));

    const again = turnOn(true);
    act(() => registerTurn(again));
    act(() => settleTurn(again));
    act(() => abortTurn("saved"));
    expect(container.textContent).not.toContain("Awaiting reply");
  });
  it("history-derived waiting state does not overwrite a running turn or mark an answer unread", () => {
    show(false);
    const turn: LiveTurn = {
      sessionId: "saved",
      controller: new AbortController(),
      steeringTurnId: "running",
      thoughts: new Map(),
      host: null,
      messages: [],
      scope: { actor: "test-login", spaceId: "space-1", agentInstanceId: "agent-1" },
      detachedCallbacks: {},
    };
    act(() => {
      registerTurn(turn);
      setSessionAwaitingInput("saved", true);
    });
    expect(container.textContent).toContain("Answer in progress");
    expect(container.textContent).not.toContain("Awaiting reply");
    act(() => {
      settleTurn(turn);
      setSessionAwaitingInput("saved", true);
    });
    expect(container.textContent).toContain("Awaiting reply");
    expect(container.querySelector('[class*="unreadDot"]')).toBeNull();
    act(() => setSessionAwaitingInput("saved", false));
    expect(container.textContent).not.toContain("Awaiting reply");
  });
  it("marks a conversation unread when its turn ends out of sight, until it is opened", () => {
    show(false);
    const settled = vi.fn();
    const unsubscribe = subscribeBackgroundSettled(settled);
    const turn: LiveTurn = {
      sessionId: "saved",
      controller: new AbortController(),
      steeringTurnId: "steering",
      thoughts: new Map(),
      host: null,
      messages: [],
      scope: { actor: "test-login", spaceId: "space-1", agentInstanceId: "agent-1" },
      detachedCallbacks: {},
      completed: true,
    };
    act(() => registerTurn(turn));
    act(() => settleTurn(turn));
    unsubscribe();
    expect(settled).toHaveBeenCalledWith(turn);
    expect(container.querySelector('[data-unread="true"]')!.textContent).toContain("Unread");
    expect(container.querySelector('[class*="unreadDot"]')).not.toBeNull();
    expect(container.querySelector('[title="Answer ready"]')).not.toBeNull();
    act(() => markSessionRead("saved"));
    expect(container.querySelector('[data-unread="true"]')).toBeNull();
    expect(container.querySelector('[class*="unreadDot"]')).toBeNull();
  });
  it.each([
    ["en", "Awaiting reply"],
    ["fr", "Réponse attendue"],
  ])("keeps the %s waiting label visible below metadata without adding a button", async (language, label) => {
    await labels.changeLanguage(language);
    const question: LiveTurn = {
      sessionId: "saved",
      controller: new AbortController(),
      steeringTurnId: "question",
      thoughts: new Map(),
      host: null,
      messages: [],
      scope: { actor: "test-login", spaceId: "space-1", agentInstanceId: "agent-1" },
      detachedCallbacks: {},
      awaitingInput: true,
    };
    act(() => {
      registerTurn(question);
      settleTurn(question);
    });
    show(false);
    const chip = container.querySelector('[class*="awaitingInput"]')!;
    expect(chip.textContent).toBe(label);
    expect(chip.parentElement!.querySelector('[class*="meta"]')).not.toBeNull();
    expect(chip.closest("a")?.getAttribute("href")).toBe("/conversation?session=saved");
    expect(chip.querySelector("button")).toBeNull();
    expect(container.querySelector('[class*="unreadDot"]')).toBeNull();
    show(true);
    expect(container.querySelector('[class*="awaitingInput"]')).toBeNull();
  });
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
    show(true, null, "Full preserved assistant name");
    const link = container.querySelector("a")!;
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
      link.focus();
    });
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe(
      "Full preserved assistant name - Agent deleted - read-only conversation",
    );
    act(() => link.blur());
    act(() => link.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe(
      "Full preserved assistant name - Agent deleted - read-only conversation",
    );
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
