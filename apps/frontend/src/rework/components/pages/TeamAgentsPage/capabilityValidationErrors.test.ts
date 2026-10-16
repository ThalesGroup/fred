// Copyright Thales 2026

import { createInstance } from "i18next";
import { describe, expect, it } from "vitest";
import en from "../../../../locales/en/translation.json";
import fr from "../../../../locales/fr/translation.json";
import { capabilityValidationErrorText } from "./capabilityValidationErrors";

describe("configuration validation transport feedback", () => {
  it.each(["en", "fr"])("translates distinct safe errors in %s", async (language) => {
    const i18n = createInstance();
    await i18n.init({ lng: language, resources: { en: { translation: en }, fr: { translation: fr } } });
    const messages = ["unavailable", "timeout", "interrupted"].map((kind) => {
      const code = `capability_validation_${kind}`;
      return capabilityValidationErrorText({ data: { detail: { code, message: "http://private/ secret" } } }, i18n.t);
    });
    expect(new Set(messages).size).toBe(3);
    for (const message of messages) {
      expect(message).toBeTruthy();
      expect(message).not.toMatch(/http|secret|capability_validation/);
    }
  });
  it("leaves unrelated validation errors to the existing fallback", () => {
    const i18n = createInstance();
    expect(capabilityValidationErrorText({ data: { detail: "Invalid template" } }, i18n.t)).toBeUndefined();
    expect(capabilityValidationErrorText(null, i18n.t)).toBeUndefined();
  });
});
