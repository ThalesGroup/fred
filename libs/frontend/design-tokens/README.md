# `@fred/design-tokens`

Framework-independent FRED design tokens with optional self-hosted Geist fonts.

```css
@import "@fred/design-tokens/tokens.css";
```

Set `data-theme="light"` or `data-theme="dark"` on the consumer document root.
The token stylesheet does not load fonts or mutate shell layout.

Consumers that want the packaged Geist files opt in separately:

```css
@import "@fred/design-tokens/fonts.css";
```

The package has no runtime dependencies. See the package's `LICENSE`,
`THIRD_PARTY_NOTICES.md`, and `licenses/Geist-OFL-1.1.txt` for distribution
terms.

The checked-in manifest uses a development coordinate for archive validation. Future release
coordinates come from a maintainer-confirmed release contract; see [../RELEASE.md](../RELEASE.md).
