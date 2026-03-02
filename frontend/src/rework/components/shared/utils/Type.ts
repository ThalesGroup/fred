export type Type = "primary" | "secondary" | "tertiary" | "error" | "success" | "warning" | "info" | "on-surface";
export type ButtonVariant = "filled" | "outlined" | "text";
export type ButtonSize = "medium" | "small";
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
  | "arrow_drop_down";
export type CustomIconType = (typeof customIcons)[number];
export type IconType = MaterialIconType | CustomIconType;

export const isCustomIcon = (icon: IconType): icon is CustomIconType => customIcons.includes(icon);
