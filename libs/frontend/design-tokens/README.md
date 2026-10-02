# `@fred-oss/design-tokens`

Framework-independent FRED design tokens with optional self-hosted Geist fonts.

```css
@import "@fred-oss/design-tokens/tokens.css";
```

Set `data-theme="light"` or `data-theme="dark"` on the consumer document root.
The token stylesheet does not load fonts or mutate shell layout.

Consumers that want the packaged Geist files opt in separately:

```css
@import "@fred-oss/design-tokens/fonts.css";
```

The package has no runtime dependencies. See the package's `LICENSE`,
`THIRD_PARTY_NOTICES.md`, and `licenses/Geist-OFL-1.1.txt` for distribution
terms.

The checked-in manifest uses the selected first-release coordinate. Approved candidate evidence
still requires a complete maintainer-confirmed release contract; see [../RELEASE.md](../RELEASE.md).

## Token migrations

Written so a developer, or their coding assistant, can migrate custom UI built
on these tokens. Newest change first.

### Text, outlines and cleanup (after `0.1.0-alpha.1`)

**Removed — action needed:**

| Removed token                                                     | Use instead                                                                                                    |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `--outline-retreat`                                               | `--outline-variant` on form controls (inputs, selects, switches), `--outline-muted` on containers and dividers |
| `--color-background-primary`                                      | `--surface-main`                                                                                               |
| `--color-background-secondary`                                    | `--surface-container`                                                                                          |
| `--color-background-info`                                         | `--info-container`                                                                                             |
| `--color-text-primary`                                            | `--on-surface`                                                                                                 |
| `--color-text-secondary`                                          | `--on-surface-retreat`                                                                                         |
| `--color-text-tertiary`                                           | `--on-surface-muted`                                                                                           |
| `--color-text-info`                                               | `--on-info-container`                                                                                          |
| `--color-border-secondary`                                        | `--outline-variant`                                                                                            |
| `--color-border-tertiary`                                         | `--outline-muted`                                                                                              |
| `--state-surface-main-hover`, `-pressed`, `-focused`, `-selected` | `--state-on-surface-hover`, `-pressed`, `-focused`, `-selected`                                                |

**Changed values, no action needed:** `--on-surface-retreat` light 30 → 40,
dark 70 → 75; `--on-surface-muted` light 40 → 45, dark 50 → 60;
`--outline-variant` light 70 → 80; `--outline-muted` light 80 → 88, dark 20 → 25.
New ramp step `--core-cold-grey-45`.

Also replace any surface token used as a border color (for example a table
divider drawn with `--surface-container-highest`) with `--outline-muted`.

### Surface scale rework (after `0.1.0-alpha.1`)

No token was renamed or removed, so existing CSS keeps resolving. What changed
is what the surface tokens look like, and one token was added.

**New rule, both themes:** each `surface-container-*` level sits further from
`--surface-main` than the level below it (darker in light, lighter in dark).
Before, light containers were mostly darker than the page and dark containers
lighter, so a component could recede in one theme and float in the other.

**New token:** `--surface-floating`, for anything that floats above the page
(menus, popovers, tooltips, dialogs, toasts, floating panels). Pair it with a
`--shadow-*`.

**Neutral ramp:** every `--core-cold-grey-*` step was regenerated as a discreet
blue-grey (CIE LCh chroma 1.5, hue 280°) instead of lavender, at the same
lightness. Steps `--core-cold-grey-97-5` and `--core-cold-grey-94-5` were added.

| Token                         | Light before → after | Dark before → after |
| ----------------------------- | -------------------- | ------------------- |
| `--surface-main`              | 98 → 100             | 6 → 6               |
| `--surface-container-lowest`  | 90 → 99              | 4 → 8               |
| `--surface-container-low`     | 92 → 97.5            | 8 → 10              |
| `--surface-container`         | 94 → 96              | 10 → 12             |
| `--surface-container-high`    | 96 → 94.5            | 12 → 15             |
| `--surface-container-highest` | 100 → 93             | 14 → 18             |
| `--surface-floating` (new)    | 100                  | 20                  |

**How to migrate.** Find every `--surface-*` usage in your CSS and inline
styles, identify what the element _is_, and apply this table. The left column
is the token FRED components typically used for that role before the change.

| Element role                                                         | Typical token before                                                                          | Token now                                     |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------- |
| Page background                                                      | `--surface-container-lowest`                                                                  | `--surface-main`                              |
| Element that must blend with the page (fade masks, rings, cut-outs)  | `--surface-container-lowest`                                                                  | the page's token, usually `--surface-main`    |
| Input, textarea, select, search field, tag input (bordered)          | `--surface-container-lowest`                                                                  | unchanged — keep a `--outline-variant` border |
| Inset well: code block, raw output, embedded table                   | `--surface-container-lowest`                                                                  | `--surface-container`                         |
| Zebra row                                                            | `--surface-container-lowest`                                                                  | `--surface-container-low`                     |
| Menu, popover, tooltip, dropdown, dialog, toast, floating panel      | `--surface-container-high` or `-highest` (sometimes `--surface-container`, `-low`, `-lowest`) | `--surface-floating`                          |
| Bordered content sheet on the page, nav rail, faint decorative block | `--surface-container-lowest`                                                                  | unchanged                                     |
| Card, sidebar, chip, list row, track, badge, hover, focus            | any `--surface-container-*`                                                                   | unchanged (tone shifts only)                  |

Every container level reads darker than `--surface-floating` in both themes,
so any of them can be nested in a floating element. Chart and canvas tooltips
that read a token from JavaScript count as floating too.

A positioned element (`position: absolute` or `fixed`) with a shadow is almost
always floating. A component that overrode a group or track background to
`--surface-container-lowest` to make it darker in light should drop the
override. Check every touched element in both `data-theme="light"` and
`data-theme="dark"`.
