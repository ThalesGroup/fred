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

import { alpha, createTheme } from "@mui/material/styles";

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
  components: {
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
});

export { darkTheme, lightTheme };
