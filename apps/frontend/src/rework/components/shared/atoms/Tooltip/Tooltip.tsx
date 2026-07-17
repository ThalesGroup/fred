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

import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
import styles from "./Tooltip.module.scss";

interface TooltipProps {
  text: string;
  children: ReactNode;
}

export const Tooltip = ({ text, children }: TooltipProps) => {
  const tooltipId = useId();
  // Single-element children get aria-describedby wired to the tooltip text so
  // screen readers announce it for both hover and keyboard focus (the CSS
  // already reveals the tooltip on :focus-within) — without this, role="tooltip"
  // alone isn't programmatically linked to the element it describes.
  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, { "aria-describedby": tooltipId })
    : children;

  return (
    <span className={styles["tooltip-wrapper"]}>
      {child}
      <span id={tooltipId} className={styles["tooltip-content"]} role="tooltip">
        {text}
      </span>
    </span>
  );
};
