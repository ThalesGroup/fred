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

/**
 * Material Symbols names the app supports (ligature names, snake_case).
 * Backend-declared icons (e.g. `CapabilityManifest.icon`) must use one of
 * these values; extend the list to adopt a new glyph.
 */
export const materialIcons = [
  "add",
  "home",
  "people",
  "groups",
  "database",
  "settings",
  "widgets",
  "folder",
  "delete",
  "infos",
  "person",
  "arrow_drop_down",
  "arrow_back",
  "logout",
  "dark_mode",
  "light_mode",
  "desktop_windows",
  "search",
  "more_vert",
  "more_horiz",
  "storefront",
  "edit",
  "visibility",
  "visibility_off",
  "reviews",
  "delete_forever",
  "lock",
  "mail",
  "send",
  "attach_file",
  "image",
  "chevron_right",
  "chevron_left",
  "close",
  "cloud_off",
  "edit_note",
  "tune",
  "forum",
  "build",
  "check_circle",
  "check_box",
  "check_box_outline_blank",
  "star",
  "content_copy",
  "error",
  "warning",
  "info",
  "find_in_page",
  "summarize",
  "table_chart",
  "create",
  "analytics",
  "show_chart",
  "sync_alt",
  "upload",
  "chat",
  "hub",
  "chat_bubble",
  "admin_panel_settings",
  "download",
  "auto_awesome",
  "picture_as_pdf",
  "description",
  "slideshow",
  "audio_file",
  "video_file",
  "create_new_folder",
  "refresh",
  "schedule",
  "edit_calendar",
  "expand_less",
  "expand_more",
  "map",
  "graphic_eq",
  "extension",
  "smart_toy",
  "gavel",
  "shield",
  "support_agent",
  "translate",
  "payments",
  "code",
  "campaign",
  "travel_explore",
  "cloud",
  "bug_report",
  "architecture",
  "assignment",
  "school",
  "receipt_long",
  "shopping_cart",
  "handshake",
  "request_quote",
  "history",
] as const;

export type MaterialIconType = (typeof materialIcons)[number];

export type CustomIconType = (typeof customIcons)[number];
export type IconType = MaterialIconType | CustomIconType;

export const isCustomIcon = (icon: IconType): icon is CustomIconType =>
  (customIcons as readonly string[]).includes(icon);

/**
 * Coerce an untrusted icon name (e.g. a backend-declared capability icon) to
 * a renderable IconType, falling back when the name is not in the supported
 * set — the Material Symbols ligature font would otherwise render the raw
 * string as text.
 */
export const toIconType = (icon: string, fallback: MaterialIconType): IconType =>
  (materialIcons as readonly string[]).includes(icon) || (customIcons as readonly string[]).includes(icon)
    ? (icon as IconType)
    : fallback;
