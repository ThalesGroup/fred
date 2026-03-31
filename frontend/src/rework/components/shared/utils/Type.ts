export type ColorTheme =
  | "primary"
  | "secondary"
  | "tertiary"
  | "error"
  | "success"
  | "warning"
  | "info"
  | "on-surface"
  | "on-surface-retreat";
export type ButtonVariant = "filled" | "outlined" | "text";

/**
 * Shared size scale for interactive components (Button, IconButton, ButtonGroupItem, Select…).
 *
 * | Value    | Height  | Typical use                                      |
 * |----------|---------|--------------------------------------------------|
 * | medium   | 2.5rem  | Default — primary actions, main form controls    |
 * | small    | 2rem    | Secondary actions, dense forms                   |
 * | xs       | 1.5rem  | Compact / auxiliary controls (admin toggles, …)  |
 *
 * Each component that consumes this type must implement all three sizes in its
 * SCSS module via the `data-size` attribute (atoms) or a `btn-{size}` class (Button/IconButton).
 */
export type ComponentSize = "medium" | "small" | "xs";

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
  | "storefront"
  | "edit"
  | "visibility"
  | "reviews"
  | "delete_forever";

export type CustomIconType = (typeof customIcons)[number];
export type IconType = MaterialIconType | CustomIconType;

export const isCustomIcon = (icon: IconType): icon is CustomIconType => customIcons.includes(icon);
