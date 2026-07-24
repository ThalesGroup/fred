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
  text?: string;
  /** Rich content instead of a plain text hint (e.g. a multi-row info panel).
   *  Unlike `text`, the tooltip widens to fit and wraps instead of forcing a
   *  single nowrap line. Takes precedence over `text` when both are set. */
  content?: ReactNode;
  children: ReactNode;
}

export const Tooltip = ({ text, content, children }: TooltipProps) => {
  const tooltipId = useId();
  // Single-element children get aria-describedby wired to the tooltip text so
  // screen readers announce it for both hover and keyboard focus (the CSS
  // already reveals the tooltip on :focus-within) — without this, role="tooltip"
  // alone isn't programmatically linked to the element it describes.
  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, { "aria-describedby": tooltipId })
    : children;
  const contentClasses = [styles["tooltip-content"]];
  if (content) contentClasses.push(styles["tooltip-content-rich"]);

  return (
    <span className={styles["tooltip-wrapper"]}>
      {child}
      <span id={tooltipId} className={contentClasses.join(" ")} role="tooltip">
        {content ?? text}
      </span>
    </span>
  );
};
