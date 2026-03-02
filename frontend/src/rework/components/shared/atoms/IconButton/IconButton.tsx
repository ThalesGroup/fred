import styles from "./IconButton.module.scss";
import { ButtonSize, IconButtonVariant, Type } from "../../utils/Type.ts";
import { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

interface IconButtonProps extends ComponentPropsWithoutRef<"button"> {
  color: Type;
  variant: IconButtonVariant;
  size: ButtonSize;
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
