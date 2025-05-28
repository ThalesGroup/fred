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

import { createTheme, PaletteMode } from '@mui/material/styles';
import React from "react";

// Extend MUI theme interface for custom chart colors
declare module '@mui/material/styles' {
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
      mediumGrey: string
    }
    sidebar: {
      background: string,
      activeItem: string,
      hoverColor: string
    }
    borderChip: {
      border: string
    }
    heroBackgroundGrad: {
      gradientFrom: string,
      gradientTo: string
    }
  }
  interface PaletteOptions {
    chart?: {
      primary?: string;
      secondary?: string;
      red?: string;
      green?: string;
      blue?: string;
      yellow?: string;
      orange?: string;
      veryHighBlue?: string;
      highBlue?: string;
      mediumBlue?: string;
      lowBlue?: string;
      veryLowBlue?: string;
      veryHighGreen?: string;
      highGreen?: string;
      mediumGreen?: string;
      lowGreen?: string;
      veryLowGreen?: string;
      veryHighYellow?: string;
      highYellow?: string;
      mediumYellow?: string;
      lowYellow?: string;
      veryLowYellow?: string;
      customAreaStyle?: string;
    };
  }
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
    markdown?: {
      h1?: React.CSSProperties;
      h2?: React.CSSProperties;
      h3?: React.CSSProperties;
      h4?: React.CSSProperties;
      p?: React.CSSProperties;
      code?: React.CSSProperties;
      a?: React.CSSProperties;
      ul?: React.CSSProperties;
      li?: React.CSSProperties;
    };
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

// Light Mode Palette
const lightPalette = {
  mode: 'light' as PaletteMode,
  background: {
    default: '#ffffff',
    paper: '#f4f4f4',
  },
  common: {
    white: "#fff",
    black: "#000",
  },
  primary: {
    contrastText: '#fff',
    main: '#4F83CC',
    light: '#879ed9',
    dark: '#023D54',
  },
  secondary: {
    main: '#9c27b0',
    light: '#ba68c8',
    dark: '#7b1fa2',
    contrastText: '#fff',
  },
  info: {
    main: "#6986D0",
    light: "#879ed9",
    dark: "#495d91",
    contrastText: "#fff",
  },
  warning: {
    main: "#ffbb00",
    light: "#ffd149",
    dark: "#ffc833",
    contrastText: "#fff",
  },
  error: {
    main: "#d32f2f",
    light: "#ef5350",
    dark: "#c62828",
    contrastText: "#fff",
  },
  success: {
    main: "#2e7d32",
    light: "#4caf50",
    dark: "#1b5e20",
    contrastText: "#fff",
  },
  chart: {
    primary: '#08519c',
    secondary: '#3182bd',
    green: '#4caf50',
    blue: '#1976d2',
    red: '#ef5350',
    orange: '#ffbb00',
    purple: '#9c27b0',
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
    customAreaStyle: '#0080ff4d',
    alterningBgColor1: '#ffffff1a',
    alterningBgColor2: '#c8c8c84d',
  },
  text: {
    primary: '#000',
    secondary: '#000',
    disabled: '#BDBDBD',
  },
  chip: {
    mediumGrey: "#dedfe0"
  },
  sidebar: {
    background: '#fafafaf2',
    activeItem: '#f0f0f5cc',
    hoverColor: '#00000008'
  },
  borderChip: {
    border: '#0000004d'
  },
  heroBackgroundGrad: {
    gradientFrom: '#ffffffd9',
    gradientTo: '#ffffffe6',
  }
};

// Dark Mode Palette
const darkPalette = {
  mode: 'dark' as PaletteMode,
  background: {
    default: '#1b1b1b',
    paper: '#333333',

    //default: '#2a2929',
    //paper: '#1e1e1e',
  },
  common: {
    white: "#fff",
    black: "#000",
  },
  primary: {
    contrastText: '#fff',
    main: '#6482AD',
    light: '#879ed9',
    dark: '#404040',
  },
  secondary: {
    main: '#f48fb1',
    light: '#f8bbd0',
    dark: '#c2185b',
    contrastText: '#000',
  },
  info: {
    main: "#81d4fa",
    light: "#b3e5fc",
    dark: "#0288d1",
    contrastText: "#fff",
  },
  warning: {
    main: "#ffcc80",
    light: "#ffe0b2",
    dark: "#f57c00",
    contrastText: "#fff",
  },
  error: {
    main: "#e57373",
    light: "#ef9a9a",
    dark: "#d32f2f",
    contrastText: "#fff",
  },
  success: {
    main: "#81c784",
    light: "#a5d6a7",
    dark: "#388e3c",
    contrastText: "#fff",
  },
  chart: {
    primary: '#de7d39',
    secondary: '#ffa726',
    green: '#81c784',
    blue: '#90caf9',
    red: '#ef9a9a',
    orange: '#ffcc80',
    purple: '#ce93d8',
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
    customAreaStyle: '#0080ff4d',
    alterningBgColor1: '#ffffff1a',
    alterningBgColor2: '#c8c8c84d',
  },
  text: {
    primary: '#fff',
    secondary: '#bbb',
    disabled: '#888888'
  },
  sidebar: {
    background: '#121214f2',
    activeItem :'#42424db3',
    hoverColor: '#ffffff0d'
  },
  borderChip: {
    border: '#ffffff26'
  },
  heroBackgroundGrad: {
    gradientFrom: '#191923cc',
    gradientTo: '#191923e6',
  }
};

// Define typography after palette is initialized
const lightTypography = {
  fontFamily: 'Roboto, sans-serif',
  fontSize: 12,
  h1: { fontSize: '2rem', fontWeight: 600, fontFamily: 'Roboto, sans-serif' },
  h2: { fontSize: '1.5rem', fontWeight: 500, fontFamily: 'Roboto, sans-serif' },
  body1: { fontSize: '1rem', fontWeight: 400, fontFamily: 'Roboto, sans-serif' },
  body2: { fontSize: '0.875rem', fontWeight: 400, fontFamily: 'Roboto, sans-serif' },
  markdown: {
    h1: {
      color: lightPalette.text.primary,
      lineHeight: 1.5, fontWeight: 500, fontSize: '1.2rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    h2: {
       color: lightPalette.text.primary,
      lineHeight: 1.5, fontWeight: 500, fontSize: '1.15rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    h3: {
       color: lightPalette.text.primary,
      lineHeight: 1.5, fontWeight: 400, fontSize: '1.10rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    h4: {
       color: lightPalette.text.primary,
      lineHeight: 1.5, fontWeight: 400, fontSize: '1.05rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    p: {
      lineHeight: 1.8,
      fontWeight: 400,
      fontSize: '1.1rem',
      marginBottom: '0.8rem',
      fontFamily: 'Roboto, sans-serif'
    },
    code: {
       color: lightPalette.text.primary,
      lineHeight: 1.5,
      fontSize: '0.9rem',
      borderRadius: '4px'
    },
    a: {
       color: lightPalette.text.primary,
      textDecoration: 'underline', lineHeight: 1.6, fontWeight: 400, fontSize: '0.9rem', fontFamily: 'Roboto, sans-serif'
    },
    ul: {
      color: lightPalette.text.primary,
      marginLeft: '0.2rem', lineHeight: 1.4, fontWeight: 400, fontSize: '0.9rem', fontFamily: 'Roboto, sans-serif' },
    li: {
      color: lightPalette.text.primary,
      marginBottom: '0.5rem', lineHeight: 1.4, fontSize: '0.9rem', fontFamily: 'Roboto, sans-serif' },
  },
};
const darkTypography = {
  fontFamily: 'Roboto, sans-serif',
  fontSize: 12,
  h1: { fontSize: '2rem', fontWeight: 600, fontFamily: 'Roboto, sans-serif' },
  h2: { fontSize: '1.5rem', fontWeight: 500, fontFamily: 'Roboto, sans-serif' },
  body1: { fontSize: '1rem', fontWeight: 400, fontFamily: 'Roboto, sans-serif' },
  body2: { fontSize: '0.875rem', fontWeight: 400, fontFamily: 'Roboto, sans-serif' },
  markdown: {
    h1: {
      color: darkPalette.text.primary,
      lineHeight: 1.5, fontWeight: 500, fontSize: '1.2rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    h2: {
      color: darkPalette.text.primary,
      lineHeight: 1.5, fontWeight: 500, fontSize: '1.15rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    h3: {
      color: darkPalette.text.primary,
      lineHeight: 1.5, fontWeight: 400, fontSize: '1.10rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    h4: {
      color: darkPalette.text.primary,
      lineHeight: 1.5, fontWeight: 400, fontSize: '1.05rem', marginBottom: '0.6rem', fontFamily: 'Roboto, sans-serif'
    },
    p: {
      color: darkPalette.text.primary,
      lineHeight: 1.8,
      fontWeight: 400,
      fontSize: '1.1rem',
      marginBottom: '0.8rem',
      fontFamily: 'Roboto, sans-serif'
    },
    code: {
      color: darkPalette.text.primary,
      lineHeight: 1.5,
      fontSize: '0.9rem',
      borderRadius: '4px'
    },
    a: {
      color: darkPalette.text.primary,
      textDecoration: 'underline', lineHeight: 1.6, fontWeight: 400, fontSize: '0.9rem', fontFamily: 'Roboto, sans-serif'
    },
    ul: {
      color: darkPalette.text.primary,
      marginLeft: '0.2rem', lineHeight: 1.4, fontWeight: 400, fontSize: '0.9rem', fontFamily: 'Roboto, sans-serif' },
    li: {
      color: darkPalette.text.primary,
      marginBottom: '0.5rem', lineHeight: 1.4, fontSize: '0.9rem', fontFamily: 'Roboto, sans-serif' },
  },
};

// Create themes
const lightTheme = createTheme({

  palette: lightPalette,
  typography: lightTypography,
  layout: {
    sidebarWidth: 180,
    sidebarCollapsedWidth: 80,
  },
  components: {
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          fontSize: '1.0rem',       // Adjust font size
          fontWeight: '300',        // Remove bold (use light font weight)
          color: lightPalette.primary.contrastText, // Text color
          padding: '12px 16px',      // Add comfortable padding
          borderRadius: '8px',       // Optional: rounded corners
          boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)', // Optional: subtle shadow
        },
        popper: {
          backdropFilter: 'blur(8px)', // Optional: subtle blur effect
        },
      }
    },
    MuiTypography: {
      styleOverrides: {
        root: {
          color: lightPalette.text.primary, // Set the default text color to 'text.primary'
        },
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
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          fontSize: '1.0rem',       // Adjust font size
          fontWeight: '300',        // Remove bold (use light font weight)
          color: darkPalette.primary.contrastText, // Text color
          padding: '12px 16px',      // Add comfortable padding
          borderRadius: '8px',       // Optional: rounded corners
          boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)', // Optional: subtle shadow
        },
        popper: {
          backdropFilter: 'blur(8px)', // Optional: subtle blur effect
        },
      }
    },
    MuiTypography: {
      styleOverrides: {
        root: {
          color: darkPalette.text.primary, // Set the default text color to 'text.primary'
        },
      },
    },
  },
});

export { lightTheme, darkTheme };
