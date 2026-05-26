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

import { useTheme } from "@mui/material";
import React from "react";

const DotsLoader = (props: { dotSize?: string; dotColor?: string }) => {
  const theme = useTheme();
  // Define inline styles
  const loaderStyle: React.CSSProperties = {
    display: "flex",
  };

  const dotStyle: React.CSSProperties = {
    width: props.dotSize || "5px",
    height: props.dotSize || "5px",
    margin: "0 3px",
    backgroundColor: props.dotColor || theme.palette.primary.light,
    borderRadius: "50%",
    animation: "bounce 0.6s infinite alternate",
  };

  return (
    <div style={loaderStyle}>
      <span style={{ ...dotStyle, animationDelay: "0s" }}></span>
      <span style={{ ...dotStyle, animationDelay: "0.2s" }}></span>
      <span style={{ ...dotStyle, animationDelay: "0.4s" }}></span>

      {/* Inline CSS for animation */}
      <style>
        {`
          @keyframes bounce {
            from {
              transform: translateY(0);
            }
            to {
              transform: translateY(-10px);
            }
          }
        `}
      </style>
    </div>
  );
};

export default DotsLoader;
