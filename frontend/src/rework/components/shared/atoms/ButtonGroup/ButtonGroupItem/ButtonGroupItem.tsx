import styles from "./ButtonGroupItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { ButtonSize, Type } from "@shared/utils/Type.ts";
import { ComponentPropsWithoutRef } from "react";

export interface ButtonGroupItemProps extends ComponentPropsWithoutRef<"button"> {
  label: string;
  icon?: IconProps;
}

export interface ButtonGroupItemPrivateProps {
  size: ButtonSize;
  color: Type;
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
    <button className={`${styles["button-group-item"]} ${styles[`btn-${color}`]} ${styles[`btn-${size}`]}`} {...props}>
      <div className={`${styles["state-layer"]} ${selected ? styles["selected"] : ""}`}>
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
