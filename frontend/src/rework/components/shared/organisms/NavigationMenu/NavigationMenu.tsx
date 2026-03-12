import styles from "./NavigationMenu.module.scss";
import NavigationMenuItem, {
  NavigationMenuItemProps,
} from "@shared/organisms/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";

export interface NavigationMenuProps {
  items: NavigationMenuItemProps[];
}

export default function NavigationMenu({ items }: NavigationMenuProps) {
  return (
    <div className={styles["navigation-menu-container"]}>
      {items.map((item) => {
        const key = item.type === "link" ? String(item.linkProps.to) : item.label;
        return <NavigationMenuItem key={key} selected={item.selected} {...item} />;
      })}
    </div>
  );
}
