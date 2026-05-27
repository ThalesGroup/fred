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

import { styled, Switch } from "@mui/material";
import { renderToStaticMarkup } from "react-dom/server";

// SVG pour la croix rouge
const RedCrossSVG = ({ theme }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M18 6L6 18"
      stroke={theme.palette.error.main}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M6 6L18 18"
      stroke={theme.palette.error.main}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

// SVG pour la coche verte
const GreenCheckSVG = ({ theme }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M20 6L9 17L4 12"
      stroke={theme.palette.success.main}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const convertSvg = (svg: React.ReactElement) => {
  const markup = renderToStaticMarkup(svg);
  const encoded = encodeURIComponent(markup);
  const dataUri = `url('data:image/svg+xml;utf8,${encoded}')`;
  return dataUri;
};

export const IOSSwitch = styled(Switch)(({ theme }) => ({
  width: 62, // Increased width by 20px
  height: 34, // Adjusted height proportionally
  padding: 0,
  "& .MuiSwitch-track": {
    borderRadius: 17, // Adjusted for new height
    backgroundColor: theme.palette.mode === "dark" ? theme.palette.primary.dark : theme.palette.primary.light,
    opacity: 1,
    transition: theme.transitions.create(["background-color", "opacity"], {
      duration: 500,
    }),
    "&:before, &:after": {
      content: '""',
      position: "absolute",
      transform: "translateY(-50%)",
      width: 16,
      height: 16,
      top: "50%",
      transition: "opacity 300ms",
    },
    "&:before": {
      backgroundImage: convertSvg(<RedCrossSVG theme={theme} />),
      left: 8,
      opacity: 1,
    },
    "&:after": {
      backgroundImage: convertSvg(<GreenCheckSVG theme={theme} />),
      right: 8,
      opacity: 0,
    },
  },
  "& .MuiSwitch-thumb": {
    boxSizing: "border-box",
    width: 30, // Adjusted thumb size
    height: 30, // Adjusted thumb size
    "&:before": {
      content: "''",
      position: "absolute",
      width: "100%",
      height: "100%",
      left: 0,
      top: 0,
      backgroundRepeat: "no-repeat",
      backgroundPosition: "center",
      backgroundImage: convertSvg(<RedCrossSVG theme={theme} />),
      transition: "background-image 300ms",
    },
  },
  "& .MuiSwitch-switchBase": {
    padding: 0,
    margin: 2,
    transitionDuration: "300ms",
    "&.Mui-checked": {
      transform: "translateX(28px)", // Adjusted for new width
      color: "#fff",
      "& + .MuiSwitch-track": {
        backgroundColor: theme.palette.success.main,
        opacity: 1,
        border: 0,
        "&:before": {
          opacity: 0,
        },
        "&:after": {
          opacity: 1,
        },
      },
      "& .MuiSwitch-thumb:before": {
        content: "''",
        position: "absolute",
        width: "100%",
        height: "100%",
        left: 0,
        top: 0,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "center",
        backgroundImage: convertSvg(<GreenCheckSVG theme={theme} />),
      },
    },
    "&.Mui-disabled + .MuiSwitch-track": {
      opacity: 0.5,
    },
    "&:not(.Mui-checked) + .MuiSwitch-track": {
      backgroundColor: theme.palette.error.main,
    },
  },
}));
