// @vitest-environment happy-dom
// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createInstance, type i18n } from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";
import { selectedSkillText } from "@rework/utils/skillInvocation";
import { SkillBadge } from "./SkillBadge";
import { TraceEntryRow } from "../ThoughtTrace/TraceEntryRow/TraceEntryRow";
import SkillDetailPanel from "../SkillDetailPanel/SkillDetailPanel";
import { UserMessage } from "../UserMessage/UserMessage";
import { toThreadMessages } from "@rework/components/pages/ManagedChatPage/toThreadMessages";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let root: Root;
let container: HTMLDivElement;
let language: i18n;
const onOpen = vi.fn();

beforeEach(async () => {
  language = createInstance();
  await language.use(initReactI18next).init({
    lng: "fr",
    fallbackLng: "en",
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  onOpen.mockClear();
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(builtin?: boolean, name = "meeting-minutes") {
  act(() =>
    root.render(
      <I18nextProvider i18n={language}>
        <div data-skill-message>
          <SkillBadge name={name} description="Authored description" builtin={builtin} onOpen={onOpen} />
        </div>
      </I18nextProvider>,
    ),
  );
}

it("updates packaged presentation with the interface language while preserving invocation and copied identity", async () => {
  render(true);
  const button = container.querySelector("button")!;
  expect(button.textContent).toContain("Compte rendu de réunion");
  expect(button.title).toBe(`Compte rendu de réunion: ${fr.chatbot.skills.catalog["meeting-minutes"].description}`);
  act(() => button.click());
  expect(onOpen).toHaveBeenCalledWith("meeting-minutes");
  const range = document.createRange();
  range.selectNodeContents(container.querySelector("[data-skill-message]")!);
  expect(selectedSkillText(range, container)).toBe("/meeting-minutes");
  const label = container.querySelector("[data-skill-name]")!;
  range.selectNodeContents(label);
  expect(selectedSkillText(range, container)).toBe("/meeting-minutes");
  await act(() => language.changeLanguage("en"));
  expect(button.textContent).toContain("Meeting minutes");
  expect(button.title).toBe(`Meeting minutes: ${en.chatbot.skills.catalog["meeting-minutes"].description}`);
});

it("preserves authored custom skills and histories without packaged provenance", () => {
  for (const builtin of [false, undefined]) {
    render(builtin);
    expect(container.querySelector("button")?.textContent).toBe("meeting-minutes");
    expect(container.querySelector("button")?.title).toContain("Authored description");
  }
});

it("falls back to English, then authored metadata for an untranslated packaged skill", async () => {
  language.removeResourceBundle("fr", "translation");
  render(true);
  expect(container.textContent).toContain("Meeting minutes");
  render(true, "future-skill");
  expect(container.textContent).toBe("future-skill");
  expect(container.querySelector("button")?.title).toContain("Authored description");
});

it("localizes successful activity and historical invocations only from trusted load provenance", async () => {
  const user: ChatMessage = {
    session_id: "session",
    exchange_id: "exchange",
    rank: 0,
    timestamp: "2026-10-27T00:00:00Z",
    role: "user",
    channel: "final",
    parts: [{ type: "text", text: "/meeting-minutes Notes" }],
    metadata: { extras: { skill_invocations: [{ name: "meeting-minutes" }] } },
  };
  const load: ChatMessage = {
    ...user,
    rank: 1,
    role: "assistant",
    channel: "system_note",
    parts: [],
    metadata: { extras: { skill_load: { name: "meeting-minutes", origin: "user", load_id: "load", builtin: true } } },
  };
  const [turn] = toThreadMessages([user, load], false);
  act(() =>
    root.render(
      <I18nextProvider i18n={language}>
        <UserMessage {...turn} />
        <TraceEntryRow entry={{ kind: "solo", message: load }} />
        <TraceEntryRow
          entry={{
            kind: "solo",
            message: {
              ...load,
              metadata: { extras: { skill_load: { name: "meeting-minutes", origin: "agent", load_id: "old" } } },
            },
          }}
        />
      </I18nextProvider>,
    ),
  );
  expect(container.querySelector('[data-kind="skill"]')?.textContent).toContain("Compte rendu de réunion");
  expect(container.querySelector('button[aria-label="Skill chargé: Compte rendu de réunion"]')).not.toBeNull();
  expect(container.querySelector('button[aria-label="Skill chargé: meeting-minutes"]')).not.toBeNull();
  await act(() => language.changeLanguage("en"));
  expect(container.querySelector('[data-kind="skill"]')?.textContent).toContain("Meeting minutes");
  expect(container.querySelector('button[aria-label="Skill loaded: Meeting minutes"]')).not.toBeNull();
});

it("localizes detail metadata while preserving the English body and argument hints", () => {
  act(() =>
    root.render(
      <I18nextProvider i18n={language}>
        <SkillDetailPanel
          open
          name="meeting-minutes"
          loading={false}
          error={false}
          onClose={vi.fn()}
          onRetry={vi.fn()}
          detail={{
            skill: {
              name: "meeting-minutes",
              description: "Authored English metadata",
              builtin: true,
              argument_hint: "[meeting notes]",
            },
            revision: "v1",
            content: "# Instructions\nPreserve confirmed decisions.",
          }}
        />
      </I18nextProvider>,
    ),
  );
  expect(container.textContent).toContain("Compte rendu de réunion");
  expect(container.textContent).toContain("décisions confirmées");
  expect(container.textContent).toContain("[meeting notes]");
  expect(container.textContent).toContain("Preserve confirmed decisions.");
});
