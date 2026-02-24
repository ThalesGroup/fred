import styles from "./NavigationMenuItem.module.scss";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { Link } from "react-router-dom";

export interface NavigationMenuItemProps {
  label: string;
  icon: IconProps;
  selected: boolean;
  link: string;
}
export default function NavigationMenuItem({ label, icon, selected, link }: NavigationMenuItemProps) {
  return (
    <Link to={link}>
      <span className={`${styles["navigation-menu-item"]} ${selected ? styles["selected"] : ""}`}>
        <span className={styles["icon"]}>
          <Icon {...icon} />
        </span>
        <span className={styles["label"]}>{label}</span>
      </span>
    </Link>
  );
}
