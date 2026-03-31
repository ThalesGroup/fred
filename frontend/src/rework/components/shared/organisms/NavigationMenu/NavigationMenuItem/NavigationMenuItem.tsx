import styles from "./NavigationMenuItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { LinkProps, NavLink } from "react-router-dom";

export interface NavigationMenuItemBase {
  label: string;
  icon: IconProps;
}

export interface NavigationLinkProps extends NavigationMenuItemBase {
  type: "link";
  linkProps: LinkProps;
}

export interface NavigationActionProps extends NavigationMenuItemBase {
  type: "button";
  onClick: () => void;
  selected: boolean;
}

export type NavigationMenuItemProps = NavigationLinkProps | NavigationActionProps;

export default function NavigationMenuItem({ label, icon, ...props }: NavigationMenuItemProps) {
  const Content = (
    <>
      <span className={styles.icon} aria-hidden="true">
        <Icon {...icon} />
      </span>
      <span className={styles.label}>{label}</span>
    </>
  );

  if (props.type === "link") {
    return (
      <NavLink
        to={props.linkProps.to}
        end={false}
        children={({ isActive }) => (
          <div className={styles["navigation-menu-item"]} data-selected={isActive}>
            {Content}
          </div>
        )}
      />
    );
  }

  return (
    <button
      type="button"
      className={styles["navigation-menu-item"]}
      onClick={props.onClick}
      data-selected={props.selected}
      aria-selected={props.selected}
    >
      {Content}
    </button>
  );
}
