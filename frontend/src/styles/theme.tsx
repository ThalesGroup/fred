// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { createTheme, PaletteMode } from "@mui/material/styles";
import React from "react";

/**
 * Fred rationale:
 * - We treat the "hero" gradient as the canonical tinted surface for dark (and light) UI.
 * - Surfaces are centralized as palette tokens so components can reference them consistently.
 * - Minimalism over magic: two surfaces (soft/raised) cover 95% of use cases.
 */

// ---------- Type Augmentation ----------
declare module "@mui/material/styles" {
  interface Palette {
    chart: {
      primary: string;
      secondary: string;
      red: string;
      green: string;
      blue: string;
      yellow: string;
      orange: string;
      veryHighBlue: string;
      highBlue: string;
      mediumBlue: string;
      lowBlue: string;
      veryLowBlue: string;
      veryHighGreen: string;
      highGreen: string;
      mediumGreen: string;
      lowGreen: string;
      veryLowGreen: string;
      veryHighYellow: string;
      highYellow: string;
      mediumYellow: string;
      lowYellow: string;
      veryLowYellow: string;
      customAreaStyle: string;
      alterningBgColor1: string;
      alterningBgColor2: string;
    };
    chip: {
      mediumGrey: string;
    };
    sidebar: {
      background: string;
      activeItem: string;
      hoverColor: string;
    };
    borderChip: {
      border: string;
    };
    heroBackgroundGrad: {
      gradientFrom: string;
      gradientTo: string;
    };
    /** Reusable container surfaces derived from hero gradient */
    surfaces: {
      soft: string;
      raised: string;
    };
  }
  interface PaletteOptions {
    chart?: Partial<Palette["chart"]>;
    chip?: Partial<Palette["chip"]>;
    sidebar?: Partial<Palette["sidebar"]>;
    borderChip?: Partial<Palette["borderChip"]>;
    heroBackgroundGrad?: Partial<Palette["heroBackgroundGrad"]>;
    surfaces?: Partial<Palette["surfaces"]>;
  }

  interface TypographyVariants {
    sidebar: React.CSSProperties;
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
    sidebar?: React.CSSProperties;
    markdown?: Partial<TypographyVariants["markdown"]>;
  }

  interface Theme {
    layout: {
      sidebarWidth: number;
      sidebarCollapsedWidth: number;
    };
  }
  interface ThemeOptions {
    layout?: {
      sidebarWidth?: number;
      sidebarCollapsedWidth?: number;
    };
  }
}

declare module "@mui/material/Typography" {
  interface TypographyPropsVariantOverrides {
    sidebar: true;
  }
}

// ---------- Shared Gradient Stops (single source of truth) ----------
const lightHeroFrom = "#ffffffd9";
const lightHeroTo   = "#ffffffe6";

const darkHeroFrom  = "#191923cc";
const darkHeroTo    = "#191923e6";

// ---------- Light Palette ----------
const lightPalette = {
  mode: "light" as PaletteMode,
  background: {
    default: "#ffffff",
    paper: "#f4f4f4",
  },
  common: { white: "#fff", black: "#000" },
  primary: { contrastText: "#fff", main: "#4F83CC", light: "#879ed9", dark: "#023D54" },
  secondary: { main: "#9c27b0", light: "#ba68c8", dark: "#7b1fa2", contrastText: "#fff" },
  info: { main: "#6986D0", light: "#879ed9", dark: "#495d91", contrastText: "#fff" },
  warning: { main: "#ffbb00", light: "#ffd149", dark: "#ffc833", contrastText: "#fff" },
  error: { main: "#d32f2f", light: "#ef5350", dark: "#c62828", contrastText: "#fff" },
  success: { main: "#2e7d32", light: "#4caf50", dark: "#1b5e20", contrastText: "#fff" },
  chart: {
    primary: "#08519c",
    secondary: "#3182bd",
    green: "#4caf50",
    blue: "#1976d2",
    red: "#ef5350",
    orange: "#ffbb00",
    purple: "#9c27b0",
    yellow: "#ffd149",
    veryHighBlue: "#08519c",
    highBlue: "#3182bd",
    mediumBlue: "#6baed6",
    lowBlue: "#bdd7e7",
    veryLowBlue: "#eff3ff",
    veryHighGreen: "#006d2c",
    highGreen: "#31a354",
    mediumGreen: "#74c476",
    lowGreen: "#bae4b3",
    veryLowGreen: "#edf8e9",
    veryHighYellow: "#de7d39",
    highYellow: "#fe9929",
    mediumYellow: "#ffbb00",
    lowYellow: "#fed98e",
    veryLowYellow: "#ffffd4",
    customAreaStyle: "#0080ff4d",
    alterningBgColor1: "#ffffff1a",
    alterningBgColor2: "#c8c8c84d",
  },
  text: { primary: "#000", secondary: "#000", disabled: "#BDBDBD" },
  chip: { mediumGrey: "#dedfe0" },
  sidebar: { background: "#fafafaf2", activeItem: "#f0f0f5cc", hoverColor: "#00000008" },
  borderChip: { border: "#0000004d" },
  heroBackgroundGrad: { gradientFrom: lightHeroFrom, gradientTo: lightHeroTo },
  // Surfaces derived from hero gradient to keep consistency with the welcome box
  surfaces: {
    soft:   `linear-gradient(180deg, ${lightHeroFrom}, ${lightHeroTo})`,
    raised: `linear-gradient(180deg, #ffffffcc, #f7f7f7f2)`,
  },
};

// ---------- Dark Palette ----------
const darkPalette = {
  mode: "dark" as PaletteMode,
  background: {
    default: "#1b1b1b",
    paper: "#333333",
  },
  common: { white: "#fff", black: "#000" },
  primary: { contrastText: "#fff", main: "#6482AD", light: "#879ed9", dark: "#404040" },
  secondary: { main: "#f48fb1", light: "#f8bbd0", dark: "#c2185b", contrastText: "#000" },
  info: { main: "#81d4fa", light: "#b3e5fc", dark: "#0288d1", contrastText: "#fff" },
  warning: { main: "#ffcc80", light: "#ffe0b2", dark: "#f57c00", contrastText: "#fff" },
  error: { main: "#e57373", light: "#ef9a9a", dark: "#d32f2f", contrastText: "#fff" },
  success: { main: "#81c784", light: "#a5d6a7", dark: "#388e3c", contrastText: "#fff" },
  chart: {
    primary: "#de7d39",
    secondary: "#ffa726",
    green: "#81c784",
    blue: "#90caf9",
    red: "#ef9a9a",
    orange: "#ffcc80",
    purple: "#ce93d8",
    yellow: "#ffe082",
    veryHighBlue: "#0d47a1",
    highBlue: "#64b5f6",
    mediumBlue: "#64b5f6",
    lowBlue: "#e3f2fd",
    veryLowBlue: "#e3f2fd",
    veryHighGreen: "#1b5e20",
    highGreen: "#388e3c",
    mediumGreen: "#66bb6a",
    lowGreen: "#a5d6a7",
    veryLowGreen: "#c8e6c9",
    veryHighYellow: "#ff6f00",
    highYellow: "#ffa726",
    mediumYellow: "#ffb74d",
    lowYellow: "#ffe082",
    veryLowYellow: "#fff3e0",
    customAreaStyle: "#0080ff4d",
    alterningBgColor1: "#ffffff1a",
    alterningBgColor2: "#c8c8c84d",
  },
  text: { primary: "#fff", secondary: "#bbb", disabled: "#888888" },
  sidebar: { background: "#121214f2", activeItem: "#42424db3", hoverColor: "#ffffff0d" },
  borderChip: { border: "#ffffff26" },
  heroBackgroundGrad: { gradientFrom: darkHeroFrom, gradientTo: darkHeroTo },
  // Surfaces derived from hero gradient (the subtle blue you liked)
  surfaces: {
    soft:   `linear-gradient(180deg, ${darkHeroFrom}, ${darkHeroTo})`,
    raised: `linear-gradient(180deg, #1f2230cc, #1b1f2ae6)`,
  },
};

// ---------- Typography ----------
const baseTypography = {
  fontFamily: "Inter, sans-serif",
  fontSize: 12,
  sidebar: {
    fontSize: "14px",
    fontWeight: 300,
    lineHeight: 1.5,
    fontFamily: "Inter, sans-serif",
  },
  h1: { fontSize: "2rem", fontWeight: 600 },
  h2: { fontSize: "1.5rem", fontWeight: 500 },
  body1: { fontSize: "1rem", fontWeight: 400 },
  body2: { fontSize: "0.875rem", fontWeight: 400 },
  markdown: {
    h1: { lineHeight: 1.5, fontWeight: 500, fontSize: "1.2rem", marginBottom: "0.6rem" },
    h2: { lineHeight: 1.5, fontWeight: 500, fontSize: "1.15rem", marginBottom: "0.6rem" },
    h3: { lineHeight: 1.5, fontWeight: 400, fontSize: "1.10rem", marginBottom: "0.6rem" },
    h4: { lineHeight: 1.5, fontWeight: 400, fontSize: "1.05rem", marginBottom: "0.6rem" },
    p:  { lineHeight: 1.8, fontWeight: 400, fontSize: "1.0rem", marginBottom: "0.8rem" },
    code: { lineHeight: 1.5, fontSize: "0.9rem", borderRadius: "4px" },
    a: { textDecoration: "underline", lineHeight: 1.6, fontWeight: 400, fontSize: "0.9rem" },
    ul: { marginLeft: "0.2rem", lineHeight: 1.4, fontWeight: 400, fontSize: "0.9rem" },
    li: { marginBottom: "0.5rem", lineHeight: 1.4, fontSize: "0.9rem" },
  },
};

const lightTypography = {
  ...baseTypography,
  sidebar: { ...baseTypography.sidebar, color: lightPalette.text.secondary },
  markdown: Object.fromEntries(
    Object.entries(baseTypography.markdown).map(([k, v]) => [
      k,
      { ...v, color: lightPalette.text.primary, fontFamily: "Inter, sans-serif" },
    ]),
  ),
};

const darkTypography = {
  ...baseTypography,
  sidebar: { ...baseTypography.sidebar, color: darkPalette.text.secondary },
  markdown: Object.fromEntries(
    Object.entries(baseTypography.markdown).map(([k, v]) => [
      k,
      { ...v, color: darkPalette.text.primary, fontFamily: "Inter, sans-serif" },
    ]),
  ),
};

// ---------- Theme Factories ----------

const lightTheme = createTheme({
  palette: lightPalette,
  typography: lightTypography,
  layout: {
    sidebarWidth: 180,
    sidebarCollapsedWidth: 80,
  },
  components: {
    // Keep your existing overrides...
    MuiTooltip: {
      defaultProps: {
        arrow: true,
        disableInteractive: true,
        enterDelay: 900,
        enterNextDelay: 200,
        leaveDelay: 100,
        enterTouchDelay: 800,
        leaveTouchDelay: 3000,
      },
      styleOverrides: {
        tooltip: {
          fontSize: "1.0rem",
          fontWeight: "300",
          backgroundColor: lightPalette.background.paper,
          color: lightPalette.text.primary,
          padding: "12px 16px",
          borderRadius: "8px",
          boxShadow: "0px 2px 4px rgba(0, 0, 0, 0.1)",
          maxWidth: 360,
        },
        arrow: { color: lightPalette.background.paper },
      },
    },
    MuiTypography: {
      styleOverrides: {
        root: { color: lightPalette.text.primary },
      },
      variants: [
        {
          props: { variant: "sidebar" },
          style: {
            fontSize: "14px",
            fontWeight: 300,
            lineHeight: 1.5,
            fontFamily: "Inter, sans-serif",
            color: lightPalette.text.secondary,
          },
        },
      ],
    },

    // Apply the subtle hero-tinted surfaces globally
    MuiPaper: {
      styleOverrides: {
        root: ({ theme }) => ({
          background: theme.palette.surfaces.soft,
          border: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
    MuiCard: {
      styleOverrides: {
        root: ({ theme }) => ({
          background: theme.palette.surfaces.raised,
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: 16,
        }),
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: ({ theme }) => ({
          background: theme.palette.surfaces.soft,
          borderRight: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: ({ theme }) => ({
          background: theme.palette.surfaces.soft,
          backdropFilter: "saturate(120%) blur(6px)",
          boxShadow: "none",
          borderBottom: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
  },
});

const darkTheme = createTheme({
  palette: darkPalette,
  typography: darkTypography,
  layout: {
    sidebarWidth: 180,
    sidebarCollapsedWidth: 80,
  },
  components: {
    // Keep your existing overrides...
    MuiTooltip: {
      defaultProps: {
        arrow: true,
        disableInteractive: true,
        enterDelay: 900,
        enterNextDelay: 200,
        leaveDelay: 100,
        enterTouchDelay: 800,
        leaveTouchDelay: 3000,
      },
      styleOverrides: {
        tooltip: {
          fontSize: "1.0rem",
          fontWeight: "300",
          backgroundColor: darkPalette.background.paper,
          color: darkPalette.text.primary,
          padding: "12px 16px",
          borderRadius: "8px",
          boxShadow: "0px 2px 4px rgba(0, 0, 0, 0.1)",
          maxWidth: 360,
        },
        arrow: { color: darkPalette.background.paper },
        popper: { backdropFilter: "blur(8px)" },
      },
    },
    MuiTypography: {
      styleOverrides: {
        root: { color: darkPalette.text.primary },
      },
      variants: [
        {
          props: { variant: "sidebar" },
          style: {
            fontSize: "14px",
            fontWeight: 300,
            lineHeight: 1.5,
            fontFamily: "Inter, sans-serif",
            color: darkPalette.text.secondary,
          },
        },
      ],
    },

    // Apply the subtle hero-tinted surfaces globally
    MuiPaper: {
      styleOverrides: {
        root: ({ theme }) => ({
          background: theme.palette.surfaces.soft,
          border: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
    MuiCard: {
      styleOverrides: {
        root: ({ theme }) => ({
          background: theme.palette.surfaces.raised,
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: 16,
        }),
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: ({ theme }) => ({
          background: theme.palette.surfaces.soft,
          borderRight: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: ({ theme }) => ({
          background: theme.palette.surfaces.soft,
          backdropFilter: "saturate(120%) blur(6px)",
          boxShadow: "none",
          borderBottom: `1px solid ${theme.palette.divider}`,
        }),
      },
    },
  },
});

export { lightTheme, darkTheme };
