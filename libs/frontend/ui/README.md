# `@fred-oss/ui`

This package is generated from FRED's canonical React components. The published
`0.1.0-alpha.1` archive contains `Button`, `IconButton`, `Icon`, `TextInput`, and
`Spinner`; the reviewed `0.1.0-alpha.2` source candidate adds `Dialog`, `Select`,
`Chip`, `Tooltip`, and `Checkbox`. This README describes the candidate API; it does
not claim that the new version has been published.

The public root exports ten component values and the reviewed `ButtonProps`,
`IconButtonProps`, `IconProps`, `TextInputProps`, `SpinnerProps`, `DialogProps`,
`SelectProps<T>`, `SelectOption<T>`, `ChipProps`, `TooltipProps`, `CheckboxProps`,
`ButtonSize`, `ButtonVariant`, `IconButtonVariant`, `ColorTheme`, and `MaterialIconType` contracts.
No component subpath is public.

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
Sharp, custom SVG icons, deferred components, other overlays, iframe SDK work, this
version's publication, and adopter migrations are outside this extension milestone.

The checked-in manifest uses the selected UI-only prerelease coordinate. Release candidates must still
be compared with a complete, maintainer-confirmed contract as described in
[../RELEASE.md](../RELEASE.md).
