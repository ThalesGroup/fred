## Context

See proposal.md - Why. The neutral ramp lives in `apps/frontend/src/styles/color-ramps.css` as `--core-cold-grey-<tone>` hex values; `colors-semantic-light.css` and `colors-semantic-dark.css` map semantic tokens onto it under `[data-theme]`. Nothing else defines these tokens (no copy in `@fred-oss/ui`).

Light currently orders containers "higher = lighter" (90 → 100) around a tone-98 background, dark orders them "higher = lighter" (4 → 14) around a tone-6 background. The background sits near the top of the scale in light and near the bottom in dark, which is what makes the switch look broken. Components picked their level by how it looked in light, so `surface-container-lowest` (the darkest light level) is used for filled fields and code wells, and `surface-container-highest` (white in light) for menus and tooltips.

## Goals / Non-Goals

**Goals:** one rule, two themes; a cleaner light neutral; every remapped usage keeps or improves its current visual role.

**Non-Goals:** renaming the container tokens; touching text, outline, accent or state tokens beyond the hue shift they inherit from the ramp.

## Decisions

**Scale "further from the background" (M3 semantics, softened light steps).** Chosen over "higher = lighter" with a lowered light background (keeps today's intuition but light steps 97–100 are too close to tell apart) and over a role-based 4-token scale (cleaner but a ~300-usage rename). Light steps are 1.5 tones apart instead of M3's 2 to avoid heavy greys.

**A dedicated `--surface-floating` token.** Under this scale no container level is both near-white in light and clearly raised in dark. Using `surface-container` (strict M3) makes menus grey in light; using `surface-container-lowest` leaves dark menus at tone 8, distinguishable only by shadow. One named exception (light 100, dark 15) is clearer than bending a container level.

**Ramp generated once, committed as hex.** Each step is CIE LCh(L = tone, C = 1.5, H = 280°) converted to sRGB (D65). Values are computed once and written to `color-ramps.css` with a 2-line comment giving the formula; no generator script is added. Tone 0 and 100 stay pure black and white. Half steps are named `--core-cold-grey-97-5` and `--core-cold-grey-94-5`. No existing step is removed, even unused ones.

**Remap by role, not by token name.** Each `surface-container-lowest` and `surface-container-highest` usage is reassigned by what the element is:

| Role | Today | New token | Examples |
|---|---|---|---|
| Page or content background | `surface-container-lowest` | `surface-main` | `styles.css` body, Gdpr/Gcu/ReleaseNotes/Bootstrap/TeamAdminCharter contents, DocumentViewerPage |
| Element that must blend with the page behind it | `surface-container-lowest` | the token of that page (usually `surface-main`) | HorizontalScrollRow fade, TraceEntryRow dot ring, ChatList sticky group header |
| Filled field | `surface-container-lowest` | `surface-container-highest` | TextInput (incl. autofill), TextArea, DateTimeInput, Select, SearchField, TagInput, PromptEditor, PromptViewDialog textarea |
| Inset well (code, raw output, tables) | `surface-container-lowest` | `surface-container` | CodeBlock (CSS and `customStyle`), TabularToolDetail, PlatformPromptPage instructions, MindMapBlock chart pane, LibraryTreePlayground card |
| Zebra row | `surface-container-lowest` | `surface-container-low` | MarkdownRenderer even rows |
| Main nav | `surface-container-lowest` | `surface-container-low` | MainNavBar |
| Floating element | `surface-container-highest` or `surface-container-lowest` | `surface-floating` | Menu, Tooltip, WritableDocumentPane mdx popup and tooltip, SourceDetailModal |
| Track, badge, hover, focus, pending row | `surface-container-highest` | unchanged | ProgressBar, TaskProgressBar, badges, TimeRangeSelector hover, RichInputField/HomeSearch focus, CleanupDialog header, TaskTray/UserProfile trigger, AddTeamMembers pending row |

Usages not listed (TeamSettings panels, AgentCard disabled icon, DocumentUploadDrawer/CreateFolderModal path, WikiEditor toolbar, MindMapBlock gradient) are classified with the same table during apply, by looking at the element in both themes.

## Risks / Trade-offs

- [Filled fields get lighter in dark (4 → 18)] → matches M3 filled fields; checked visually on a form page in both themes.
- [Borders drawn with `surface-container-highest` become visible lines in light (DataTable, TablePagination)] → accepted; revisited by the outline follow-up.
- [Hue shift reaches text and outlines too] → same tones, so contrast ratios are unchanged within rounding; spot-checked with a contrast tool.
- [Usages read only in light during review] → every remapped component is checked in both themes before close-out.

## Migration Plan

Frontend-only CSS change, shipped with the next frontend release; rollback is a revert of the commits. Commits are split: (1) ramp regeneration, (2) semantic token values + `surface-floating`, (3) usage remap.
