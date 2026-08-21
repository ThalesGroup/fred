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
 * | Value    | Typical use                                              |
 * |----------|----------------------------------------------------------|
 * | medium   | Default — primary actions, main form controls            |
 * | small    | Secondary actions, dense forms                           |
 * | xs       | Compact controls / dense fields (e.g. nav-panel search)  |
 * | 2xs      | Extra-compact auxiliary controls (row action icons, …)   |
 *
 * NOTE (#2298 / #2299): the concrete pixel height a value maps to still differs
 * per component (a known scale inconsistency #2299 will unify) — e.g. `xs` is
 * 2rem/32px on TextInput and Select but buttons express 32px through `small`.
 * `2xs` (added #2298) is the 1.5rem/24px tier that used to be called `xs` on
 * Button/IconButton/ButtonGroupItem/TextInput; those call sites were migrated so
 * `xs` could become the 32px "compact field" tier the Home nav-panel search
 * needs. A component only needs to implement the sizes it actually offers — not
 * every value maps to a rule in every component.
 */
export type ComponentSize = "medium" | "small" | "xs" | "2xs";

export type IconButtonVariant = "filled" | "tonal" | "outlined" | "icon";
export type IconCategory = "outlined" | "rounded" | "sharp";

const customIcons = ["customAgent"] as const;

/**
 * Material Symbols names the app supports (ligature names, snake_case).
 * Backend-declared icons (e.g. `CapabilityManifest.icon`) must use one of
 * these values; extend the list to adopt a new glyph.
 */
export const materialIcons = [
  "add",
  "crown",
  "remove",
  "home",
  "people",
  "groups",
  "database",
  "settings",
  "widgets",
  "neurology",
  "radio_button_unchecked",
  "folder",
  "delete",
  "infos",
  "person",
  "person_add",
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
  "first_page",
  "last_page",
  "close",
  "cloud_off",
  "edit_note",
  "tune",
  "forum",
  "build",
  "check",
  "check_circle",
  "check_box",
  "check_box_outline_blank",
  "star",
  "content_copy",
  "error",
  "error_outline",
  "warning",
  "info",
  "find_in_page",
  "summarize",
  "table_chart",
  "table",
  "article",
  "draft",
  "create",
  "analytics",
  "show_chart",
  "sync_alt",
  "sync",
  "upload",
  "upload_file",
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
  "keyboard_arrow_down",
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
  "category",
  "notes",
  "drive_file_rename_outline",
  "search_off",
  "arrow_upward",
  "arrow_downward",
  "bar_chart",
  "help",
  "help_center",
  "link",
  "rocket_launch",
  "quiz",
  "new_releases",
  "login",
  "mic",
  "stop",
  "book_2",
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
