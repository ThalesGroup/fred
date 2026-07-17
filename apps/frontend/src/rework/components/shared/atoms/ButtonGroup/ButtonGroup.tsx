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

import styles from "./ButtonGroup.module.scss";
import ButtonGroupItem, { ButtonGroupItemProps } from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import { ComponentSize, ColorTheme } from "@shared/utils/Type.ts";
import { useState } from "react";

interface ButtonGroupProps {
  items: ButtonGroupItemProps[];
  size: ComponentSize;
  color: ColorTheme;
  defaultSelectedIndex?: number;
  /** When provided, turns the component into a controlled tab strip. */
  selectedIndex?: number;
  onSelectedIndexChange?: (index: number) => void;
}

export default function ButtonGroup({
  items,
  size,
  color,
  defaultSelectedIndex = 0,
  selectedIndex,
  onSelectedIndexChange,
}: ButtonGroupProps) {
  const [internalIndex, setInternalIndex] = useState(defaultSelectedIndex);
  const resolvedIndex = selectedIndex !== undefined ? selectedIndex : internalIndex;

  return (
    <div className={styles["button-group"]} role="radiogroup">
      {items.map((item, index) => (
        <ButtonGroupItem
          key={index}
          {...item}
          size={size}
          color={color}
          selected={index === resolvedIndex}
          onClick={(e) => {
            setInternalIndex(index);
            onSelectedIndexChange?.(index);
            if (item.onClick) {
              item.onClick(e);
            }
          }}
        />
      ))}
    </div>
  );
}
