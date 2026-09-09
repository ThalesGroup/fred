# `@fred/ui`

This package contains the first application-agnostic React components generated from
FRED's canonical implementations: `Button`, `IconButton`, `Icon`, `TextInput`, and
`Spinner`. It is an archive foundation for external consumers, not yet a published npm
release.

The public root exports the five component values and the reviewed `ButtonProps`,
`IconButtonProps`, `IconProps`, `TextInputProps`, `SpinnerProps`, `ButtonSize`,
`ButtonVariant`, `IconButtonVariant`, `ColorTheme`, and `MaterialIconType` contracts.
No component subpath is public.

Install this archive together with the matching `@fred/design-tokens` archive and
consumer-owned React 19.2.4 / React DOM 19.2.4. Import the contracts explicitly:

```tsx
import { Button, Icon, TextInput } from "@fred/ui";
import "@fred/design-tokens/tokens.css";
import "@fred/ui/styles.css";
```

Wrap reusable UI in a consumer-owned `.fred-ui` root and set `data-theme="light"` or
`data-theme="dark"` on that root or an ancestor. The UI stylesheet includes component
CSS and the packaged Material Symbols Outlined font. It does not apply FRED shell-wide
rules. Icons are decorative unless `accessibleName` is supplied, and only names in the
exported `MaterialIconType` are supported.

Geist remains optional. Import `@fred/design-tokens/fonts.css` only when the consumer
wants the packaged Geist faces, then set its own font-family policy.

The producer's separate provisioning commands populate a lockfile-pinned dependency
cache and install Chromium. Offline validation then creates a fresh consumer outside FRED,
installs both archives and dependencies only from that cache, type-checks and builds it,
and runs browser smoke tests without installing anything. Missing cache or browser
prerequisites are errors.

Canonical ownership, package boundaries, and future work are described by the existing
[frontend packaging RFC](https://github.com/ThalesGroup/fred/blob/swift/docs/swift/FRED-FRONTEND-PACKAGING-RFC.md). Rounded,
Sharp, custom SVG icons, deferred components, overlays, iframe SDK work, registry
publication, and adopter migrations are outside this package milestone.
