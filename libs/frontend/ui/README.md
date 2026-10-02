# `@fred-oss/ui`

This package is generated from FRED's canonical React components. The reviewed
`@fred-oss/ui@0.1.0-alpha.3` candidate extends the published alpha.2 surface for
hosted applications. Publication is a separate protected release step.

The public root exports `Button`, `Icon`, `IconButton`, `Spinner`, `TextInput`,
`Dialog`, `Select`, `Chip`, `Tooltip`, `Checkbox`, `TextArea`, `Switch`,
`ProgressBar`, `IndicatorDot`, `Disclosure`, `Breadcrumb`, `PageHeader`,
`SelectableCard`, `FileDropzone`, `ServiceNotice`, `PageEmptyState`,
`KpiStatCard`, `DataTable`, `TablePagination`, `InlineDrawer`, `Toast`,
`ToastProvider`, `useToast`, and `StatusBadge`, together with their prop and
required option/visual contracts. Generic `DataTableProps<T>` and
`DataTableColumn<T>` retain the consumer's row type. No component subpath is public.

Install this archive together with the matching `@fred-oss/design-tokens` archive and
consumer-owned React 19.2.4 / React DOM 19.2.4. Import the contracts explicitly:

```tsx
import {
  Button,
  Checkbox,
  Chip,
  Dialog,
  Icon,
  IconButton,
  Select,
  Spinner,
  TextInput,
  Tooltip,
} from "@fred-oss/ui";
import type { SelectOption } from "@fred-oss/ui";
import "@fred-oss/design-tokens/tokens.css";
import "@fred-oss/ui/styles.css";
```

`Dialog` keeps the action-oriented `open`, `title`, `confirmLabel`, `onConfirm`, and
`onCancel` contract. Supply `cancelLabel` for localized consumers (neutral default:
`Cancel`); FRED's thin application wrapper still supplies its translated default.
`Select` uses generic options with unique `key`, typed `value`, `label`, and optional
Outlined `icon`; set `emptyMessage` to localize its empty state. A removable `Chip`
defaults its button name to `Remove ${label}`, which callers can override via
`removeAriaLabel`. `Tooltip` accepts text or rich content and dismisses on Escape;
`Checkbox` retains native input props, refs, and `indeterminate`.

KPI state text is configurable through `loadingLabel`, `errorLabel`, and
`noDataLabel`. `DataTable` accepts `labels` for selection and nested `pagination`
labels; `TablePaginationLabels` includes typed `totalItems(count)` and
`pageNumber(page, pageCount)` formatters. Defaults are neutral English; FRED's
application adapters supply its existing translations. Pagination options use
`SelectOption<number>`. `ServiceNotice` and `PageEmptyState` accept only
`MaterialIconType` names.

`StatusBadge` renders a label with `success`, `error`, `warning`, `info`, or
`neutral` tone; use `Chip` for removable input tokens. `InlineDrawer` supports
both overlay and push layouts. With `resizable`, `width` must be a pixel string
(e.g. `"480px"`); other CSS units are rejected. Without resizing, CSS units remain
unrestricted. Push drawers accept `resizable` bounds and a
`persistKey`. Resize/storage hooks are private implementation dependencies.
`ToastProvider` and direct `Toast` accept `onCopy(text)`, `copyLabel`, and
`dismissLabel`. Supply your application's clipboard action to enable error
copying; without it, the copy control is omitted. `useToast` exposes success,
error, info, and warning notifications with caller-controlled expiry.

Wrap reusable UI in a consumer-owned `.fred-ui` root and set `data-theme="light"` or
`data-theme="dark"` on that root or an ancestor. The UI stylesheet includes component
CSS and the packaged Material Symbols Outlined font. It does not apply FRED shell-wide
rules. Icons are decorative unless `accessibleName` is supplied, and only names in the
exported `MaterialIconType` are supported.
Dialog, Select, and Tooltip portal within their originating `.fred-ui` root. If a
Dialog is opened programmatically outside that root, supply `portalContainer` within
the themed root. The FRED application wrapper retains body-level portals when it has
no consumer root. Dialog traps Tab focus and restores the opening trigger; an open
Select receives Escape before its parent Dialog.

Geist remains optional. Import `@fred-oss/design-tokens/fonts.css` only when the consumer
wants the packaged Geist faces, then set its own font-family policy.

The producer's separate provisioning commands populate a lockfile-pinned dependency
cache and install Chromium. Offline validation then creates a fresh consumer outside FRED,
installs both archives and dependencies only from that cache, type-checks and builds it,
and runs browser smoke tests without installing anything. Missing cache or browser
prerequisites are errors.

Canonical ownership, package boundaries, and future work are described by the existing
[frontend packaging RFC](https://github.com/ThalesGroup/fred/blob/swift/docs/swift/FRED-FRONTEND-PACKAGING-RFC.md). Rounded,
Sharp, custom SVG icons, domain-specific components, iframe SDK work, and
adopter migrations are outside this extension milestone.

The checked-in manifest uses the published UI prerelease coordinate. Future release
candidates must still be compared with a complete, maintainer-confirmed contract as described in
[../RELEASE.md](../RELEASE.md).

Real-consumer interaction props: `DataTable<T>.onRowClick(row)` activates row
background/cells by pointer or Enter/Space while leaving embedded controls alone.
When combined with selection, background activates and checkboxes select.
`InlineDrawer.closeLabel` supplies the accessible close action name.
`KpiStatCard.tone` accepts the shared `StatusBadgeTone` vocabulary and defaults to
neutral. These additive alpha.3 props preserve existing consumer defaults.

`TextArea` is controlled: pass `value` (use `""` for an empty field) and
`onChange`, or `readOnly` for display. `defaultValue` is unsupported and rejected
by the public types and at runtime, keeping the character counter tied to the
value supplied by the consumer.
