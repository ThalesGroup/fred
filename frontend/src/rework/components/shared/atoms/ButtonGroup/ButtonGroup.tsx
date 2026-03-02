import styles from "./ButtonGroup.module.scss";
import ButtonGroupItem, { ButtonGroupItemProps } from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import { ButtonSize, Type } from "@shared/utils/Type.ts";
import { useState } from "react";

interface ButtonGroupProps {
  items: ButtonGroupItemProps[];
  size: ButtonSize;
  color: Type;
  defaultSelectedIndex?: number;
}

export default function ButtonGroup({ items, size, color, defaultSelectedIndex = 0 }: ButtonGroupProps) {
  const [selectedIndex, setSelectedIndex] = useState(defaultSelectedIndex);

  return (
    <div className={styles["button-group"]}>
      {items.map((item, index) => (
        <ButtonGroupItem
          key={index}
          {...item}
          size={size}
          color={color}
          selected={index === selectedIndex}
          onClick={(e) => {
              console.log("click");
            setSelectedIndex(index);
            if (item.onClick) {
              item.onClick(e);
            }
          }}
        />
      ))}
    </div>
  );
}
