import styles from "./MarketplaceNavbar.module.scss";
import { useTranslation } from "react-i18next";
import NavigationMenu from "@shared/organisms/NavigationMenu/NavigationMenu.tsx";
import { NavigationMenuItemProps } from "@shared/organisms/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";

export default function MarketplaceNavbar() {
  const { t } = useTranslation();

  const navigationItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.sidebar.marketplace.menu.teams"),
      icon: { category: "outlined", type: "groups", filled: true },
      linkProps: { to: "/marketplace/teams" },
    },
    /*
    {
      type: "link",
      label: t("rework.sidebar.marketplace.menu.agents"),
      icon: { category: "outlined", type: "person" },
      linkProps: { to: "/marketplace/agents" },
    },
*/
  ];

  return (
    <div className={styles["marketplace-navbar-container"]}>
      <div className={styles["marketplace-navbar-title"]}>{t("rework.sidebar.marketplace.title")}</div>
      <NavigationMenu items={navigationItems}></NavigationMenu>
    </div>
  );
}
