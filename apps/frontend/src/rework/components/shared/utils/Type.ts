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

const customIcons = ["customAgent"] as const;

export type MaterialIconType =
  | "add"
  | "home"
  | "people"
  | "groups"
  | "settings"
  | "widgets"
  | "folder"
  | "delete"
  | "infos"
  | "person"
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
  | "visibility_off"
  | "reviews"
  | "delete_forever"
  | "lock"
  | "mail"
  | "send"
  | "attach_file"
  | "image"
  | "chevron_right"
  | "chevron_left"
  | "close"
  | "cloud_off"
  | "edit_note"
  | "tune"
  | "forum"
  | "build"
  | "check_circle"
  | "content_copy"
  | "error"
  | "warning"
  | "info"
  | "find_in_page"
  | "summarize"
  | "table_chart"
  | "create"
  | "analytics"
  | "show_chart"
  | "sync_alt"
  | "chat"
  | "hub"
  | "chat_bubble"
  | "admin_panel_settings"
  | "download"
  | "auto_awesome"
  | "picture_as_pdf"
  | "description"
  | "slideshow"
  | "audio_file"
  | "video_file"
  | "create_new_folder"
  | "refresh"
  | "schedule"
  | "edit_calendar"
  | "expand_less"
  | "expand_more";

export type CustomIconType = (typeof customIcons)[number];
export type IconType = MaterialIconType | CustomIconType;

export const isCustomIcon = (icon: IconType): icon is CustomIconType =>
  (customIcons as readonly string[]).includes(icon);
