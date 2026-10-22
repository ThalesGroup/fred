// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { MermaidConfig } from "mermaid";
import { supportsBeautifulMermaid } from "./mermaidCompatibility";
import { sanitizeMermaidForParsing } from "./mermaidSanitizer";

export const MERMAID_TOKENS = {
  bg: "--surface-container",
  fg: "--on-surface",
  line: "--on-surface-retreat",
  accent: "--primary",
  muted: "--on-surface-retreat",
  surface: "--surface-container-high",
  border: "--outline-variant",
} as const;

export interface MermaidTheme {
  colors: Record<keyof typeof MERMAID_TOKENS, string>;
  font: string;
  dark: boolean;
  secondary: string;
  tertiary: string;
}

/** Read effective deployment/shipped tokens from the mounted diagram's theme. */
export function readMermaidTheme(element: HTMLElement): MermaidTheme {
  const styles = getComputedStyle(element);
  return {
    colors: Object.fromEntries(
      Object.entries(MERMAID_TOKENS).map(([key, token]) => [key, styles.getPropertyValue(token).trim()]),
    ) as MermaidTheme["colors"],
    font: styles
      .getPropertyValue("--font-family-base")
      .split(",")[0]
      .trim()
      .replace(/^["']|["']$/g, ""),
    dark: document.documentElement.dataset.theme === "dark",
    secondary: styles.getPropertyValue("--secondary").trim(),
    tertiary: styles.getPropertyValue("--tertiary").trim(),
  };
}

// Mermaid's initialization is global; keep configuration and rendering atomic across blocks.
let compatibilityQueue: Promise<unknown> = Promise.resolve();

function renderCompatibility(code: string, id: string, theme: MermaidTheme): Promise<string> {
  const result = compatibilityQueue.then(async () => {
    const { default: mermaid } = await import("mermaid");
    const { bg, fg, line, accent, surface, border } = theme.colors;
    const config: MermaidConfig = {
      startOnLoad: false,
      securityLevel: "strict",
      suppressErrorRendering: true,
      secure: ["securityLevel", "startOnLoad", "theme", "themeVariables", "fontFamily"],
      theme: "base",
      fontFamily: theme.font,
      themeVariables: {
        darkMode: theme.dark,
        background: bg,
        fontFamily: theme.font,
        primaryColor: surface,
        primaryTextColor: fg,
        primaryBorderColor: border,
        secondaryColor: surface,
        secondaryTextColor: fg,
        secondaryBorderColor: border,
        tertiaryColor: bg,
        tertiaryTextColor: fg,
        tertiaryBorderColor: border,
        lineColor: line,
        textColor: fg,
        mainBkg: surface,
        nodeBorder: border,
        clusterBkg: bg,
        clusterBorder: border,
        edgeLabelBackground: bg,
        titleColor: fg,
        pie1: accent,
        pie2: theme.secondary,
        pie3: theme.tertiary,
        pieStrokeColor: border,
        pieSectionTextColor: fg,
        pieLegendTextColor: fg,
      },
    };
    mermaid.initialize(config);
    try {
      return (await mermaid.render(id, code)).svg;
    } finally {
      document.getElementById(`d${id}`)?.remove();
    }
  });
  compatibilityQueue = result.catch(() => undefined);
  return result;
}

/** Prefer themed SVGs, preserving raw-first Mermaid compatibility before syntax repair. */
export async function renderMermaid(code: string, id: string, theme: MermaidTheme): Promise<string> {
  let lastError: unknown;
  async function attempt(source: string, suffix: string): Promise<string> {
    if (supportsBeautifulMermaid(source)) {
      try {
        const { renderMermaidSVGAsync } = await import("beautiful-mermaid");
        return await renderMermaidSVGAsync(source, {
          ...Object.fromEntries(Object.entries(MERMAID_TOKENS).map(([key, token]) => [key, `var(${token})`])),
          font: theme.font,
          transparent: true,
        });
      } catch (error) {
        lastError = error;
      }
    }
    return renderCompatibility(source, `${id}${suffix}`, theme);
  }
  try {
    return await attempt(code, "Raw");
  } catch (error) {
    lastError = error;
  }
  const repaired = sanitizeMermaidForParsing(code);
  if (repaired !== code) return attempt(repaired, "Repaired");
  throw lastError;
}
