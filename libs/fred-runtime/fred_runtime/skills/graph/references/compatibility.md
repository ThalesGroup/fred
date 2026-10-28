# Compatibility and rendering

## Installed baseline

The chat uses Mermaid 11.16.1, with beautiful-mermaid 1.1.3 preferred for an
evaluated subset of flowchart, sequence, state, class, entity relationship and
XY syntax. Other types or syntax outside that subset use the official Mermaid
renderer. Falling back is normal and does not mean the type is unsupported.

The renderer first tries the original source. A best-effort syntax repair runs
only after failure; produce valid source rather than relying on repair.
Parser acceptance establishes syntax, not readable layout or complete rendering.
Do not claim validation unless the available parser or renderer was actually run.

The examples in syntax-and-examples.md target this installed version. Official
live documentation may describe a newer major release; consult the linked
11.16.1 documentation for version-sensitive features.

## Advanced types and unavailable extensions

The installed package also recognizes specialist types such as
`architecture-beta`, `swimlane-beta`, `radar-beta`, `treeView-beta`,
`sankey-beta`, `packet-beta`, `block-beta` and `eventmodeling`. Recognition is
not a guarantee that an arbitrary example renders correctly. Use specialist
syntax only when the request needs it, check the installed version's official
documentation and validate when tools permit. A beta suffix alone does not mean
that a type is absent.

`usecase-beta` requires Mermaid 12.0 or newer and is unavailable in this baseline.
ZenUML needs an external module and registration that this chat does not supply.
`agentflow` is not a recognized diagram declaration here. Choose a supported
representation that preserves the requested meaning, or explain the limitation.
Do not install extensions or assume arbitrary icon packs have been registered.

Sources: [11.16.1 diagram registration](https://github.com/mermaid-js/mermaid/blob/mermaid%4011.16.1/packages/mermaid/src/diagram-api/diagram-orchestration.ts),
[use case version requirement](https://mermaid.js.org/syntax/usecase.html),
[ZenUML registration](https://mermaid.js.org/syntax/zenuml.html#integration-with-your-library-website),
[architecture syntax](https://github.com/mermaid-js/mermaid/blob/mermaid%4011.16.1/packages/mermaid/src/docs/syntax/architecture.md).

## Labels, presentation and resources

Preserve meaningful accents and other Unicode in display labels. For example,
flowcharts support `A["Demande reçue"]`; ASCII-only labels are not a Mermaid
requirement. Use the quoting rules of the chosen type rather than applying
flowchart node syntax to every diagram. Keep labels short; explain detail in
the surrounding prose. Let the chat control theme, fonts and layout defaults.

The official renderer uses strict security settings. Generated SVGs from both
renderers are sanitized and their identifiers/styles scoped before display.
These controls do not make remote resources safe or guarantee an offline result:
external image URLs can survive SVG sanitization. Use text and built-in shapes;
avoid external images, remote icons, HTML, scripts, click handlers and theme or
security overrides in generated diagrams.

Deliver the diagram in a complete `mermaid` fence, including when its first line
is `mindmap`. A fence labeled `mindmap` selects a different chat component.
An HTML artifact viewer does not execute Mermaid source. Keep engine details
out of the caption unless the user requests source, format or implementation
information.

Sources: [Unicode flowchart labels](https://github.com/mermaid-js/mermaid/blob/mermaid%4011.16.1/packages/mermaid/src/docs/syntax/flowchart.md#unicode-text),
[Mermaid security levels](https://mermaid.js.org/config/usage.html#securitylevel).
