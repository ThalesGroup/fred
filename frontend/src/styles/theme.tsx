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

const lightTheme = createTheme({
  palette: {
    mode: "light",
    secondary: {
      main: "#2f3475ff",
    },
  },
  typography: {
    markdown: markdownDefaults,
  },
  components: {
    ...sharedComponents,
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

const darkTheme = createTheme({
  palette: {
    mode: "dark",
    secondary: {
      main: "#a2a9ffff",
    },
  },
  typography: {
    markdown: markdownDefaults,
  },
  components: sharedComponents,
});

export { darkTheme, lightTheme };
