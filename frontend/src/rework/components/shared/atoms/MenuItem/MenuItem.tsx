import { ComponentPropsWithRef, memo, ReactNode, useId } from "react";
import styles from "./MenuItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface MenuItemProps extends ComponentPropsWithRef<"li"> {
  label?: string;
  children?: ReactNode;
  icon?: IconProps;
  role?: "option" | "menuitem";
  selected?: boolean;
  focused?: boolean;
  disabled?: boolean;
}

function MenuItem({
  label,
  children,
  icon,
  role = "option",
  selected = false,
  focused = false,
  disabled = false,
  onClick,
  id: providedId,
  ref, // La ref arrive ici
  ...rest
}: MenuItemProps) {
  const generatedId = useId();
  const id = providedId ?? generatedId;

  return (
    <li
      {...rest}
      ref={ref}
      id={id}
      className={styles["menu-item"]}
      role={role}
      aria-selected={role === "option" ? selected : undefined}
      aria-disabled={disabled}
      data-selected={selected}
      data-focused={focused}
      data-disabled={disabled}
      tabIndex={focused ? 0 : -1}
      onClick={disabled ? undefined : onClick}
    >
      <div className={styles["state-layer"]}>
        {icon && (
          <span className={styles["icon-wrapper"]} aria-hidden="true">
            <Icon {...icon} />
          </span>
        )}

        {children ? children : <span className={styles["label"]}>{label}</span>}
      </div>
    </li>
  );
}

export default memo(MenuItem);
