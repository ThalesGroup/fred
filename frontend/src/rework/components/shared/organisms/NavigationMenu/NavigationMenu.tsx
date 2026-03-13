import styles from "./NavigationMenu.module.scss";
import NavigationMenuItem, {
  NavigationMenuItemProps,
} from "@shared/organisms/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import { useLocation } from "react-router-dom";

export interface NavigationMenuProps {
  items: NavigationMenuItemProps[];
}

export default function NavigationMenu({ items }: NavigationMenuProps) {
  const { pathname } = useLocation();

  return (
    <div className={styles["navigation-menu-container"]}>
      {items.map(({ selected, ...item }) => (
        <NavigationMenuItem key={item.link} selected={pathname.startsWith(item.link)} {...item} />
      ))}
    </div>
  );
}
