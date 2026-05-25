// Copyright Thales 2026
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

import { PropsWithChildren } from "react";
import styles from "./AccentBar.module.css";

type AccentColor = "primary" | "error" | "success" | "warning" | "on-surface";

const COLOR_TOKEN: Record<AccentColor, string> = {
  primary: "var(--primary)",
  error: "var(--error)",
  success: "var(--success)",
  warning: "var(--warning, var(--error))",
  "on-surface": "var(--on-surface-retreat)",
};

interface AccentBarProps {
  color?: AccentColor;
  className?: string;
}

export function AccentBar({ color = "primary", children, className }: PropsWithChildren<AccentBarProps>) {
  return (
    <div
      className={`${styles.bar} ${className ?? ""}`}
      style={{ "--accent-color": COLOR_TOKEN[color] } as React.CSSProperties}
    >
      {children}
    </div>
  );
}
