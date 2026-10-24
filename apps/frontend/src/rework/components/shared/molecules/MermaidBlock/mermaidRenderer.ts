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
  palette: { background: string; text: string }[];
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
    palette: ["primary", "secondary", "tertiary"].map((role) => ({
      background: styles.getPropertyValue(`--${role}`).trim(),
      text: styles.getPropertyValue(`--on-${role}`).trim(),
    })),
  };
}

// Mermaid's initialization is global; keep configuration and rendering atomic across blocks.
let compatibilityQueue: Promise<unknown> = Promise.resolve();

function renderCompatibility(code: string, id: string, theme: MermaidTheme): Promise<string> {
  const result = compatibilityQueue.then(async () => {
    const { default: mermaid } = await import("mermaid");
    const { bg, fg, line, surface, border } = theme.colors;
    // Override all sections: Mermaid otherwise darkens its generated mindmap palette to black.
    const sectionColors = Object.fromEntries(
      Array.from({ length: 12 }, (_, index) => {
        const color = theme.palette[index % theme.palette.length];
        return [
          [`cScale${index}`, color.background],
          [`cScaleLabel${index}`, color.text],
          [`cScaleInv${index}`, line],
          [`pie${index + 1}`, color.background],
        ];
      }).flat(),
    );
    const config: MermaidConfig = {
      startOnLoad: false,
      securityLevel: "strict",
      suppressErrorRendering: true,
      secure: ["securityLevel", "startOnLoad", "theme", "themeVariables", "themeCSS", "fontFamily"],
      theme: "base",
      fontFamily: theme.font,
      // Timeline's axis otherwise inherits the text color intended for its filled nodes.
      themeCSS: `.lineWrapper line { stroke: ${line}; }`,
      themeVariables: {
        ...sectionColors,
        ...Object.fromEntries(
          Array.from({ length: 6 }, (_, index) => [
            `actor${index}`,
            theme.palette[index % theme.palette.length].background,
          ]),
        ),
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
        pieOpacity: 1,
        pieStrokeColor: border,
        pieSectionTextColor: fg,
        pieLegendTextColor: fg,
      },
    };
    mermaid.initialize(config);
    try {
      const rendered = await mermaid.render(id, code);
      if (rendered.diagramType !== "pie") return rendered.svg;
      // Pie exposes only one label color. Match each rendered slice, including omitted zero values.
      const template = document.createElement("template");
      template.innerHTML = rendered.svg;
      const labels = template.content.querySelectorAll<SVGTextElement>("text.slice");
      template.content.querySelectorAll(".pieCircle").forEach((slice, index) => {
        const color = theme.palette.find((entry) => entry.background === slice.getAttribute("fill"));
        if (color && labels[index]) labels[index].style.fill = color.text;
      });
      return template.innerHTML;
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
