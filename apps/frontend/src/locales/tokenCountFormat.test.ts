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

// #2403: token counts are five-digit numbers read at a glance. Without
// i18next's `number` format specifier, `{{count}}` interpolates the raw
// integer, so the conversation header rendered "Total : 55735 tokens" beside
// a badge whose arrows WERE grouped ("↑19 424") — the same quantity shown two
// ways in one screen. These keys must keep `{{count, number}}`; dropping the
// specifier is an easy, silent regression in a translation edit.

import i18n, { type i18n as I18n } from "i18next";
import { beforeAll, describe, expect, it } from "vitest";
import en from "./en/translation.json";
import fr from "./fr/translation.json";

const TOKEN_COUNT_KEYS = [
  "chatbot.conversationTokenUsage.total",
  "chatbot.conversationTokenUsage.cached",
  "chatbot.conversationTokenUsage.sent",
  "chatbot.conversationTokenUsage.received",
] as const;

const instances: Record<string, I18n> = {};

beforeAll(async () => {
  for (const lng of ["en", "fr"]) {
    const instance = i18n.createInstance();
    await instance.init({
      lng,
      resources: { en: { translation: en }, fr: { translation: fr } },
      interpolation: { escapeValue: false },
    });
    instances[lng] = instance;
  }
});

describe("token count strings apply locale thousands grouping", () => {
  for (const key of TOKEN_COUNT_KEYS) {
    it(`${key} groups in French`, () => {
      const rendered = instances.fr.t(key, { count: 55735 });
      // "55735" ungrouped means the `, number` specifier was lost.
      expect(rendered).not.toContain("55735");
      expect(rendered).toContain((55735).toLocaleString("fr"));
    });

    it(`${key} groups in English`, () => {
      const rendered = instances.en.t(key, { count: 55735 });
      expect(rendered).not.toContain("55735");
      expect(rendered).toContain("55,735");
    });
  }

  it("still selects the singular form, which the format specifier must not break", () => {
    expect(instances.en.t("chatbot.conversationTokenUsage.total", { count: 1 })).toBe("Total: 1 token");
    expect(instances.fr.t("chatbot.conversationTokenUsage.total", { count: 1 })).toBe("Total : 1 token");
  });

  it("renders the whole header line as one grouped figure", () => {
    expect(instances.fr.t("chatbot.conversationTokenUsage.total", { count: 55735 })).toBe(
      `Total : ${(55735).toLocaleString("fr")} tokens`,
    );
  });
});
