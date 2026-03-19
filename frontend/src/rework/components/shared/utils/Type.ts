export type ColorTheme = "primary" | "secondary" | "tertiary" | "error" | "success" | "warning" | "info" | "on-surface";
export type ButtonVariant = "filled" | "outlined" | "text";
export type ComponentSize = "medium" | "small";
export type IconButtonVariant = "filled" | "outlined" | "icon";
export type IconCategory = "outlined" | "rounded" | "sharp";

const customIcons = [];

export type MaterialIconType =
  | "Add"
  | "Home"
  | "People"
  | "Groups"
  | "Settings"
  | "Widgets"
  | "Folder"
  | "Delete"
  | "Infos"
  | "Person"
  | "arrow_drop_down"
  | "arrow_back"
  | "logout"
  | "dark_mode"
  | "light_mode"
  | "desktop_windows"
  | "search"
  | "more_vert"
  | "more_horiz"
  | "storefront";

export type CustomIconType = (typeof customIcons)[number];
export type IconType = MaterialIconType | CustomIconType;

export const isCustomIcon = (icon: IconType): icon is CustomIconType => customIcons.includes(icon);
