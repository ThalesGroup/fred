// Copyright Thales 2025
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

import { alpha, createTheme, TypographyVariants } from "@mui/material/styles";

// Resolves a CSS variable (e.g. "--primary") to its computed hex value at runtime.
// MUI requires real color values (not CSS variable references) for palette entries
// because it performs alpha/contrast calculations at theme-creation time.
function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ------------------------------------------------------------
// Extending MUI theme to add custom typography variant for markdown rendering
// ------------------------------------------------------------

declare module "@mui/material/styles" {
  interface TypographyVariants {
    markdown: {
      h1: React.CSSProperties;
      h2: React.CSSProperties;
      h3: React.CSSProperties;
      h4: React.CSSProperties;
      p: React.CSSProperties;
      code: React.CSSProperties;
      a: React.CSSProperties;
      ul: React.CSSProperties;
      li: React.CSSProperties;
    };
  }

  interface TypographyVariantsOptions {
    markdown?: Partial<TypographyVariants["markdown"]>;
  }
}

declare module "@mui/material/Typography" {
  interface TypographyPropsVariantOverrides {
    poster: true;
    h3: false;
  }
}

const markdownDefaults: TypographyVariants["markdown"] = {
  h1: { lineHeight: 1.5, fontWeight: 500, fontSize: "1.2rem", marginBottom: "0.6rem" },
  h2: { lineHeight: 1.5, fontWeight: 500, fontSize: "1.15rem", marginBottom: "0.6rem" },
  h3: { lineHeight: 1.5, fontWeight: 400, fontSize: "1.10rem", marginBottom: "0.6rem" },
  h4: { lineHeight: 1.5, fontWeight: 400, fontSize: "1.05rem", marginBottom: "0.6rem" },
  p: { lineHeight: 1.8, fontWeight: 400, fontSize: "1.0rem", marginBottom: "0.8rem" },
  code: { lineHeight: 1.5, fontSize: "0.9rem", borderRadius: "4px" },
  a: { textDecoration: "underline", lineHeight: 1.6, fontWeight: 400, fontSize: "0.9rem" },
  ul: { marginLeft: "0.2rem", lineHeight: 1.4, fontWeight: 400, fontSize: "0.9rem" },
  li: { marginBottom: "0.5rem", lineHeight: 1.4, fontSize: "0.9rem" },
};

// ------------------------------------------------------------
// Component style overrides shared between light and dark themes
// ------------------------------------------------------------

const sharedComponents = {
  // Remove border from Drawers
  MuiDrawer: {
    styleOverrides: {
      paper: {
        borderRight: "none",
        borderLeft: "none",
      },
    },
  },
};

// MUI's original elevation overlay formula (from getOverlayAlpha.js)
function getOverlayAlpha(elevation: number): number {
  let alphaValue: number;
  if (elevation < 1) {
    alphaValue = 5.11916 * elevation ** 2;
  } else {
    alphaValue = 4.5 * Math.log(elevation + 1) + 2;
  }
  return Math.round(alphaValue * 10) / 1000;
}

// ------------------------------------------------------------
// Light theme
// ------------------------------------------------------------

// Themes are factory functions (not constants) so that createTheme runs inside
// a React render, where the DOM and data-theme attribute are already set and
// cssVar() can resolve the correct computed values.

function createLightTheme() {
  return createTheme({
    palette: {
      mode: "light",
      primary: { main: cssVar("--primary"), contrastText: cssVar("--on-primary") },
      secondary: { main: cssVar("--secondary"), contrastText: cssVar("--on-secondary") },
      error: { main: cssVar("--error"), contrastText: cssVar("--on-error") },
      warning: { main: cssVar("--warning"), contrastText: cssVar("--on-warning") },
      info: { main: cssVar("--info"), contrastText: cssVar("--on-info") },
      success: { main: cssVar("--success"), contrastText: cssVar("--on-success") },
      background: { default: cssVar("--surface-main"), paper: cssVar("--surface-container") },
      text: {
        primary: cssVar("--on-surface"),
        secondary: cssVar("--on-surface-retreat"),
        disabled: cssVar("--on-surface-muted"),
      },
      divider: cssVar("--outline"),
    },
    typography: {
      markdown: markdownDefaults,
    },
    components: {
      ...sharedComponents,
      // In MUI, on dark theme, when Paper uses elevation, a white overlay is applied to lighten the Paper color.
      // On light theme, there is no such Paper color modification by default (it only add shadows).
      // To make design easier and more consistent between light and dark themes, we apply here a similar logic on light theme,
      // but using a black overlay to slightly darken the Paper color when elevation is used.
      // (note: there is no need to apply this logic to the dark theme, as MUI already does it by default, we are noly mimicking it on light theme).
      MuiPaper: {
        styleOverrides: {
          root: ({ ownerState }) => {
            // Apply the same elevation overlay logic as dark mode, but with black instead of white
            if (ownerState.variant === "elevation" && ownerState.elevation && ownerState.elevation > 0) {
              const overlayColor = alpha("#000", getOverlayAlpha(ownerState.elevation));
              return {
                backgroundImage: `linear-gradient(${overlayColor}, ${overlayColor})`,
              };
            }
            return {};
          },
        },
      },
    },
  });
}

// ------------------------------------------------------------
// Dark theme
// ------------------------------------------------------------

function createDarkTheme() {
  return createTheme({
    palette: {
      mode: "dark",
      primary: { main: cssVar("--primary"), contrastText: cssVar("--on-primary") },
      secondary: { main: cssVar("--secondary"), contrastText: cssVar("--on-secondary") },
      error: { main: cssVar("--error"), contrastText: cssVar("--on-error") },
      warning: { main: cssVar("--warning"), contrastText: cssVar("--on-warning") },
      info: { main: cssVar("--info"), contrastText: cssVar("--on-info") },
      success: { main: cssVar("--success"), contrastText: cssVar("--on-success") },
      background: { default: cssVar("--surface-main"), paper: cssVar("--surface-container") },
      text: {
        primary: cssVar("--on-surface"),
        secondary: cssVar("--on-surface-retreat"),
        disabled: cssVar("--on-surface-muted"),
      },
      divider: cssVar("--outline"),
    },
    typography: {
      markdown: markdownDefaults,
    },
    components: sharedComponents,
  });
}

// ------------------------------------------------------------
// Exporting themes
// ------------------------------------------------------------

export { createDarkTheme, createLightTheme };
