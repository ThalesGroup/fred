// Copyright Thales 2026

import type { TFunction } from "i18next";

const VALIDATION_ERRORS = new Set([
  "capability_validation_unavailable",
  "capability_validation_timeout",
  "capability_validation_interrupted",
]);

/** Translate safe, coded transport failures returned by configuration validation. */
export function capabilityValidationErrorText(error: unknown, t: TFunction): string | undefined {
  const detail = (error as { data?: { detail?: unknown } } | null)?.data?.detail;
  const code = (detail as { code?: unknown } | null)?.code;
  return typeof code === "string" && VALIDATION_ERRORS.has(code)
    ? t(`rework.agentCard.validationErrors.${code}`)
    : undefined;
}
