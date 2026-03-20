import styles from "./IconButton.module.scss";
import { ComponentSize, IconButtonVariant, ColorTheme } from "../../utils/Type.ts";
import { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface IconButtonProps extends ComponentPropsWithoutRef<"button"> {
  color: ColorTheme;
  variant: IconButtonVariant;
  size: ComponentSize;
  icon: IconProps;
}

export default function IconButton({ color, variant, size, icon, ...props }: IconButtonProps) {
  const buttonClasses = [styles.btn, styles[`btn-${color}`], styles[`btn-${size}`], styles[`btn-${variant}`]];

  return (
    <button className={buttonClasses.join(" ")} {...props}>
      <div className={`${styles["state-layer"]}`}>
        <Icon {...icon} />
      </div>
    </button>
  );
}
