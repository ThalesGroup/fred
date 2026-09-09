## Context

See `proposal.md` for motivation and
[`docs/swift/FRED-FRONTEND-PACKAGING-RFC.md`](../../../docs/swift/FRED-FRONTEND-PACKAGING-RFC.md)
for the broader package architecture.

Implementation is tracked by
[ThalesGroup/fred#2590](https://github.com/ThalesGroup/fred/issues/2590).

The private `libs/frontend` workspace currently builds and validates one individual
member, `@fred/design-tokens`. Its actual tarball is checked against an exact inventory,
complete license hashes, CSS reference closure, source-path bans, and positive and
negative fixtures. A dependency-free consumer installs that archive outside FRED, and a
separately provisioned Playwright browser checks theme and optional Geist behavior over
local-only staged output. Those guarantees are the baseline for this change, not a
surface to replace.

The selected React sources remain under `apps/frontend/src/rework/components/shared/`.
They use CSS Modules, token variables, React 19.2.4, and—in `Button` and `IconButton`—a
Sass color map from `apps/frontend/src/index.scss`. `Button` and `TextInput` depend on
`Icon`; `IconButton` depends on `Icon` and `Spinner`. None imports application state,
routing, authentication, translations, backend models, or iframe behavior.

The current icon boundary is wider than its assets. `IconCategory` declares Outlined,
Rounded, and Sharp, but the checkout has no Sharp font. The `customAgent` type enters an
absolute `/images/icons/customAgent.svg` branch, but that file does not exist. All
inspected JSX category arguments are Outlined; dynamic names enter through
`toIconType`, casts from agent configuration, capability metadata, application catalog
metadata, navigation models, and file/icon helper types. Shared `IconType` and coercion
helpers therefore have many application callers even though the package requires only
the material subset. The implementation must repeat this inventory against its working
commit before editing those shared types.

Likewise, shared `ComponentSize` includes `xs`, while `Button` and `IconButton` have no
`xs` CSS rule. The inspected literal `xs` callers target TextInput/SearchInput/Select,
not these buttons. A button-specific type can express reality without taking `xs` away
from those other controls.

## Goals / Non-Goals

**Goals:**

- Build one complete UI tarball from the same selected implementation FRED executes.
- Establish a narrow, typed, accessible, ESM-only component contract with explicit CSS.
- Prove React externalization, declaration closure, icon completeness, dual-archive
  installation, and real-browser behavior outside the producer checkout.
- Preserve the current design-token archive contract and the application's supported
  call sites while correcting the selected canonical components.

**Non-Goals:**

- Transfer canonical component ownership out of `apps/frontend`, make FRED consume a
  local or registry UI package, publish packages, or choose release ownership.
- Export deferred components, add overlays or portals, or create a provider or broader
  design-system abstraction.
- Add Rounded, Sharp, custom, remote, or consumer-hosted icon assets.
- Change RAGS, the iframe SDK, protocol version 1, origin/source validation,
  authentication, authorization, routing, backend APIs, or application registration.

## Decisions

### D1 — Export the smallest dependency-closed component set

Expose named `Button`, `IconButton`, `Icon`, `TextInput`, and `Spinner` exports and the
minimum reviewed prop and visual types needed to use them. This is one connected source
graph: Button and TextInput use Icon; IconButton uses Icon and Spinner. It exercises
native interaction, React hooks, Sass and CSS Modules, loading/error/accessibility
states, token peers, and a font asset without pulling in an unrelated component branch.

The package root is the only JavaScript entry point; `./styles.css` is the only UI style
entry point. Do not expose source or per-component subpaths. The root barrel presents
named exports even where the canonical application still uses a default import.

`TextArea` is deferred because its `height: 100%` and `resize: none` are container
policy and it has no direct tests. `Checkbox` is sounder but adds an independent label
contract not needed to prove this graph. `Switch` has no direct keyboard/semantics
tests. `Chip` permits an unnamed remove button and hides its complete leading slot from
assistive technology. `PageEmptyState` is a full-page flex molecule and inherits the
icon questions. Each can be reviewed in later issue-sized slices.

Alternative: export all RFC candidates now. Rejected because it multiplies public
accessibility and layout decisions before the archive boundary has been exercised with
React. Alternative: export only Spinner. Rejected because it would not validate the
font, Sass, forms, or meaningful component API boundaries.

### D2 — Keep application sources canonical and generate disposable package output

Add `libs/frontend/ui/` as an individual workspace member with a small maintained
public barrel and package metadata. Its build consumes an ordered allowlist of the
canonical component modules, module styles, shared visual definitions, Sass support,
Outlined font declarations, and font binary. Compilation may create a temporary source
tree or other disposable intermediates, but no component implementation is maintained
twice and no generated output is committed.

The application keeps importing the canonical files. Corrections required by this
change are made in those files and verified by both application and package tests.
Moving those sources under `libs/frontend` or replacing application imports with a
published dependency belongs to the later publication/migration slice in the RFC.

Alternative: move the source now and link `apps/frontend` to the workspace. Rejected
because a local link would not represent the eventual registry boundary and would widen
the frontend/Docker migration. Alternative: copy components into `ui/src`. Rejected
because it creates two maintained implementations immediately.

### D3 — Split the material primitive from the application icon compatibility wrapper

Do not automatically narrow or delete application-wide `IconCategory`, `IconType`,
`isCustomIcon`, or `toIconType`. First record every direct and transitive caller,
including runtime catalog, capability, and agent-supplied names, and classify whether it
is validated, coerced, or cast.

Refactor the canonical Icon module so one named material-symbol primitive owns the
Outlined rendering and accessibility behavior. The existing application-facing default
Icon may remain a thin compatibility wrapper for broader internal inputs. The
disposable package build redirects only the selected Button, IconButton, and TextInput
copies from that wrapper to the material primitive and its narrow props; their remaining
implementation stays canonical. This preserves the application's wider caller contract
without bundling it. `@fred/ui` exports that same primitive as `Icon`; it does not bundle
the application wrapper, absolute asset paths, or custom behavior. If the renewed inventory
finds a real broader application behavior, preserve it in the wrapper or make explicit,
tested caller changes rather than deleting it because the package is narrower.

The material primitive is decorative by default. A caller may opt into an informative
icon only by supplying an accessible name; it never derives localized text from the
ligature identifier. Controls own their accessible names, so their child icons remain
decorative.

Alternative: expose the current Icon unchanged. Rejected because its declared Sharp and
custom paths cannot be closed by the current archive. Alternative: remove all broader
application icon types immediately. Rejected because a public package decision does not
authorize an application behavior change.

### D4 — Correct the canonical component APIs before exporting them

Add a `ButtonSize` (or equivalently named) type for `2xs | small | medium`, derived from
but not replacing the existing `ComponentSize`. Use it in Button and IconButton and
export their props. An implementation inventory confirms that no supported button call
site passes `xs` or a wider dynamic size before this change lands.

IconButton must append a caller `className` to its generated classes and remove it from
the final native-prop spread, so neither class source overwrites the other. Its root
button consumes the focus outline variable already set by `:focus-visible`. Direct
regressions check class composition, variant/size styling, keyboard focus, loading,
busy, and disabled behavior.

TextInput resolves `effectiveId = callerId ?? generatedId`, associates its label and
error/help IDs with that value, merges caller `aria-describedby`, and applies
`aria-invalid` for an active error without overriding caller refs, handlers, input type,
autocomplete, or other native props. Controlled counts derive from `value`; uncontrolled
counts initialize from `defaultValue` and update alongside, not instead of, the caller's
change handler. The uncontrolled input also observes its owning form's native `reset`
event and, after uncancelled default reset behavior completes, synchronizes the count
from the actual input value in the next task rather than before the browser's reset
default action. A canceled reset changes neither value nor count. The
implementation composes its internal element reference with the caller's forwarded ref.
The reset listener's lifetime follows the input's controlled/uncontrolled mode rather
than every component render, so a parent state update from `onReset` cannot cancel the
pending post-reset synchronization. Cleanup still removes the listener and cancels any
pending task when the input unmounts or changes mode.
Compact presentation may hide help/error text visually but retains its ID in the input's
accessible description. Disabled error presentation follows the existing behavior.

Spinner exports its prop type and adds consumer-supplied status text, defaulting to the
existing `Loading`. Decorative mode continues to remove its role and label.

Alternative: publish current declarations and document the gaps. Rejected because these
are observable public-contract and accessibility defects, and package consumers should
not depend on known invalid states.

### D5 — Build ESM, declarations, and CSS while externalizing every React entry

Use lockfile-pinned producer tooling compatible with the checkout's TypeScript 5.9.3,
Vite 6.4.x, Sass, React 19.2.4, and matching React types. Build one ESM entry and a
closed declaration graph. The package manifest exposes:

```json
{
  ".": {
    "types": "./dist/types/src/index.d.ts",
    "import": "./dist/index.js"
  },
  "./styles.css": "./dist/styles.css"
}
```

Declare React and React DOM `^19.2.4` peers and externalize `react`, `react-dom`, and
every subpath, including `react/jsx-runtime`, `react/jsx-dev-runtime`,
`react-dom/client`, and `react-dom/server`. Treat `@fred/design-tokens` as an explicit
consumer-installed peer at the currently tested development version; choose a normal
SemVer range only in the release change. No CommonJS build or source maps enter this
initial archive.

Capture the actual module graph during the production build and fail if a React module
is internal. The archive validator separately checks all emitted bare imports against
the manifest peer allowlist; a peer declaration alone is not externalization evidence.

Alternative: bundle React for convenience. Rejected because hooks can then resolve
against multiple runtimes in one consumer. Alternative: publish source TypeScript.
Rejected because consumers must not need FRED aliases, Sass setup, or source layout.

### D6 — Keep component CSS explicit, scoped, and independent of optional Geist

Compile the allowlisted CSS Modules and Sass into `dist/styles.css`; JavaScript does not
silently load that stylesheet. Module class names stay private. Generate only the
shared base rules required to preserve component rendering—such as border-box behavior
and the existing component shape behavior—under `.fred-ui`; do not copy FRED's global
`*`, `html`, `body`, scrolling, selection, or application-shell rules.

Generate the Outlined `@font-face` and material-symbol rendering declarations from the
canonical application font inputs with package-relative URLs. UI CSS contains no
`@import` and no external URL. It consumes the existing token variable names but neither
imports token CSS nor sets `data-theme`. Consumers import `tokens.css`, then
`styles.css`, and optionally `fonts.css`. Archive validation closes every emitted
custom-property reference against declarations in those canonical token inputs or the
UI stylesheet, including neutral tonal IconButton state layers. The UI tarball does not
duplicate Geist.

Archive validation parses selectors structurally rather than searching selector text for
a generated class substring. A selector is contained only when its effective subject is
within `.fred-ui` or a generated component-class scope. Negations do not establish
containment, every branch of `:is()` or `:where()` used as a scope must be contained, and
sibling or column combinators cannot use an earlier scoped element to authorize a later
outside subject. This accepts the generated component selectors while rejecting
functional-pseudo and combinator escapes.

No selected component portals. A future portaled export must define a caller-controlled
container inside the themed `.fred-ui` root before it can join the package.

Alternative: publish `apps/frontend/src/styles/index.css`. Rejected because it contains
shell-wide layout and selection behavior. Alternative: import fonts from Google.
Rejected because archive acceptance requires complete local assets and local-only
browser execution.

### D7 — Block on verified Outlined font provenance and glyph closure

The implementation established that the canonical binary is the byte-identical
`variablefont/MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].woff2` artifact from
`google/material-design-icons` commit
`caeba1e66925218b1fd1464171f93e2656f9a0b9`. The observed canonical binary is
`apps/frontend/src/assets/fonts/material-symbols-outlined.woff2`, currently SHA-256
`98817d23c038afb643c659819b194fa4146880c54f2f14d12c1710a5c41760d7`.
`libs/frontend/ui/PROVENANCE.md` records its upstream path and blob, complete Apache
2.0 license input, packed hashes, and the verified absence of an upstream `NOTICE` at
that revision. Generation copies the canonical checkout asset after verifying this
evidence; it does not download or substitute a font. If that evidence stops matching,
the implementation remains blocked rather than guessing or replacing the asset.

Use a lockfile-pinned font inspection tool to enumerate supported ligatures/codepoints
from the canonical and packed binaries. Validate every public `MaterialIconType` name,
not only the few icons used by the fixture, and verify the packed font is byte-identical
to the approved canonical input. Rounded, Sharp, and custom assets are excluded.

Alternative: assume the repository Apache license covers the font. Rejected because the
font is a separate third-party redistribution input. Alternative: test only that a file
named `.woff2` exists. Rejected because that cannot prove the public glyph contract.

### D8 — Generalize archive safety without weakening token-specific validation

Split the current archive validator into shared archive-safety checks and explicit
package contracts. Retain the design-token contract's exact inventory, token-CSS
structure, Geist hashes/licenses, mutations, neutral consumer, and browser assertions.
The UI contract adds its own exact manifest and inventory; export and reference closure
for ESM, declarations, and CSS; peer/import consistency; React build evidence; scoped
CSS checks; font/glyph/license hashes; and source-path bans.

Runtime JavaScript closure and TypeScript declaration closure use distinct resolution
rules. A relative runtime import must resolve exactly to a packed executable JavaScript
module; a declaration file alone never satisfies it. Declaration references retain the
reviewed `.d.ts` and emitted-source mapping needed by the closed type graph.

Pack each workspace member explicitly through `npm pack --json`. A combined validation
target accepts only the two validated tarballs. Negative UI fixtures mutate disposable
archives or generated inputs, never canonical application sources.

Alternative: add UI exceptions to the hard-coded token validator. Rejected because it
would blur two different public contracts and make regressions harder to localize.

### D9 — Add a separately provisioned, offline isolated React consumer

Commit a private `fixtures/react-consumer` manifest and lockfile for React 19.2.4,
React DOM 19.2.4, TypeScript, and its production bundler. A provisioning target may
download only those lockfile-pinned dependencies into a dedicated producer-owned npm
cache from registry sources. Browser acquisition remains the existing separate pinned
Playwright provisioning step.

Validation creates a new OS temporary directory outside FRED, copies only the fixture
and the two validated tarballs, clears workspace/package environment, and invokes the
package manager in offline mode to install the pinned consumer dependencies from the
dedicated prepared cache plus both archives. This install step is expected; it neither
fetches from the network nor resolves from FRED's installed dependency tree, workspace,
or local package links. Missing cache entries or a missing provisioned browser fail
immediately with actionable setup guidance instead of triggering implicit provisioning.
Validation type-checks every public prop/type and creates a production bundle before the
browser harness sees the output. It also proves the resolved consumer graph contains one
React and that the package's CSS import is explicit.

Reuse and extend the producer-owned Playwright harness rather than adding Playwright to
the consumer. Browser smoke execution performs no dependency installation or browser
download. Fresh contexts render every component in light and dark themes, exercise
Tab/Enter/Space behavior, names, focus, class composition, disabled/loading/error
states, neutral tonal IconButton hover/pressed layers, custom/default/decorative spinner
text, material glyphs, tokens without Geist, and explicit Geist opt-in. Request
observation retains the existing bans on failures, non-2xx responses, non-loopback
traffic, `file:` URLs, checkout paths, and external font services.

Alternative: use FRED's Vite application as the consumer. Rejected because its aliases,
dependencies, and global CSS can conceal an incomplete archive. Alternative: let the
smoke target run `npm install` or download Chromium. Rejected because provisioning and
offline acceptance would no longer be distinguishable.

### D10 — Select every canonical and orchestration input

Extend the existing single frontend-package CI job rather than add another workflow.
Its tested path contract includes `libs/frontend/**`; the selected canonical TSX,
module CSS/SCSS, shared types, and Sass support; canonical icon declarations and binary;
the application manifest and lockfile that establish the React baseline; the existing
token/Geist inputs; applicable licenses/notices; and root/workflow/setup orchestration.
Representative path tests prove each category selects the job and an unrelated
application change may skip it.

After separate dependency and Chromium setup, the job runs producer quality/unit tests,
both pack checks, the neutral and React consumers, and all browser smoke checks. Because
canonical application sources change, implementation evidence also includes
`apps/frontend` quality, production build, and the relevant component and frontend
regression suite.

### D11 — Keep shipped documentation next to its owner

Extend `libs/frontend/README.md` with package build, provisioning, validation, and
canonical-input ownership. Add `libs/frontend/ui/README.md` for imports, peers,
`.fred-ui`, supported components/types, accessibility ownership, icon limits, and
optional Geist. Update `docs/swift/ux/COMPONENT-UX.md` for the actual canonical
component corrections.

The broader RFC remains open. Correct only its stale implementation status and its
suggested-location line during proposal preparation; after implementation, keep shipped
details in package documentation and leave the RFC focused on deferred components, the
iframe SDK, release/migration, and adoption.

## Risks / Trade-offs

- **A future canonical Outlined binary may no longer match the approved provenance.** →
  Keep the approved hash, upstream revision, complete license, and glyph inspection as
  blocking inputs and accept no guessed or silently substituted binary.
- **A shared icon-type cleanup could break dynamic application metadata.** → Preserve
  application-wide types and the compatibility wrapper by default; inventory and test
  every coercion/cast caller before any broader edit.
- **Generated packages tied to application sources are not final ownership.** → Keep the
  dependency one-way and allowlisted, emit no source paths, and defer transfer until FRED
  can consume a published package.
- **CSS compilation can accidentally inherit application globals.** → Generate a
  package-specific stylesheet, require `.fred-ui`, validate selectors and URLs, and
  assert document-level styles remain unchanged in a browser.
- **A build can declare React peers while still bundling React.** → Require module-graph
  evidence plus emitted-import validation and a one-React isolated consumer assertion.
- **Generalizing the validator can weaken the shipped token contract.** → Keep separate
  package policies and run the complete existing token positive/negative suite on every
  change.
- **The fixture validates one toolchain, not every React bundler.** → Limit this slice's
  compatibility claim to the pinned consumer and broaden only with additional evidence.

## Migration Plan

1. Complete the icon caller/provenance inventories and stop if the canonical font cannot
   be licensed from evidence.
2. Correct and test the selected canonical application components without moving them.
3. Add the UI member, explicit source inventory, ESM/declaration/CSS build, and bounded
   manifest.
4. Generalize archive validation, retain all token checks, and add UI positive and
   negative archive evidence.
5. Add separately provisioned dependencies, the dual-tarball isolated React consumer,
   and the extended browser harness.
6. Wire exact CI inputs, documentation, frontend regressions, strict OpenSpec validation,
   and independent implementation review.

No runtime deployment or registry migration occurs. Rollback removes the UI member and
its validation wiring and reverts the selected source corrections; the existing token
package and FRED application continue independently.

## Open Questions

- The Material Symbols provenance question is resolved for this binary by the exact
  upstream revision, blob, byte comparison, SHA-256, complete Apache 2.0 input, and
  absence-of-`NOTICE` check recorded in D7 and `libs/frontend/ui/PROVENANCE.md`. A future
  binary change must establish a new approved evidence set before generation proceeds.
- Which organization-controlled npm scope, stable/prerelease versions, publication
  owners, and support window will be used? These remain intentionally deferred to the
  publication change; `@fred/ui` and development versions are planning identities here.
