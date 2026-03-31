import styles from "./ButtonGroupItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { ComponentSize, ColorTheme } from "@shared/utils/Type.ts";
import { ComponentPropsWithoutRef } from "react";

export interface ButtonGroupItemProps extends ComponentPropsWithoutRef<"button"> {
  label: string;
  icon?: IconProps;
}

export interface ButtonGroupItemPrivateProps {
  size: ComponentSize;
  color: ColorTheme;
  selected: boolean;
}

export default function ButtonGroupItem({
  color,
  label,
  icon,
  selected,
  size,
  ...props
}: ButtonGroupItemProps & ButtonGroupItemPrivateProps) {
  return (
    <button className={styles.buttonGroupItem} data-color={color} data-size={size} {...props}>
      <div className={`${styles.stateLayer}`} data-selected={selected}>
        {icon && (
          <span className={styles.icon}>
            <Icon {...icon} />
          </span>
        )}
        <span className={styles.label}>{label}</span>
      </div>
    </button>
  );
}
