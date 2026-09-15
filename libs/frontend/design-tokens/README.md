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
