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

import { cloneElement, CSSProperties, HTMLAttributes, ReactElement, useId, useRef } from "react";
import styles from "./Tooltip.module.scss";

interface TooltipProps {
  text: string;
  children: ReactElement<HTMLAttributes<HTMLElement>>;
}

export const Tooltip = ({ text, children }: TooltipProps) => {
  const tooltipId = useId();
  const popoverRef = useRef<HTMLDivElement>(null);
  const anchorName = `--anchor-${tooltipId.replace(/:/g, "")}`;

  const childProps = children.props as HTMLAttributes<HTMLElement>;

  const tooltipHandlers = {
    style: {
      ...childProps.style,
      anchorName: anchorName,
    } as CSSProperties,
    onMouseEnter: () => popoverRef.current?.showPopover(),
    onMouseLeave: () => popoverRef.current?.hidePopover(),
    onFocus: () => popoverRef.current?.showPopover(),
    onBlur: () => popoverRef.current?.hidePopover(),
  };

  return (
    <>
      {cloneElement(children, tooltipHandlers)}

      <div
        ref={popoverRef}
        id={tooltipId}
        popover="manual"
        style={{ positionAnchor: anchorName } as CSSProperties}
        className={styles["tooltip-content"]}
      >
        {text}
      </div>
    </>
  );
};
