# Frontend Package Archives Specification

## Purpose

Defines how FRED produces and verifies self-contained frontend package archives that
external applications can install without access to the FRED source checkout.

## Requirements

### Requirement: The producer workspace is not a publishable package

The frontend package workspace root SHALL declare `private: true`, and package build,
pack, and validation operations SHALL target an individual package rather than the
workspace root. The privacy of the workspace root MUST NOT be treated as the eventual
publication setting of an individual package.

#### Scenario: The workspace root cannot be selected for publication

- **WHEN** the frontend package release inputs are enumerated
- **THEN** the private workspace root is excluded while eligible individual package
  manifests remain independently configurable for later publication

### Requirement: Package generation has one canonical source

Package generation SHALL read the existing canonical FRED design-token CSS and Geist
assets directly or consume generated intermediates derived from them. The repository
MUST NOT contain a second manually maintained copy of those source files for the
package.

#### Scenario: A canonical token changes

- **WHEN** a token value changes in its canonical FRED stylesheet and the design-token
  package is rebuilt
- **THEN** the resulting archive contains the changed value without requiring the same
  edit in another maintained stylesheet

#### Scenario: Generated output is rebuilt

- **WHEN** generated package output is removed and recreated from the checkout
- **THEN** the public package files are reproduced from canonical FRED sources rather
  than restored from a parallel maintained source tree

### Requirement: The design-token package has explicit neutral exports

The design-token package SHALL export a token stylesheet and a separate optional
Geist-font stylesheet. Importing the token stylesheet MUST preserve the existing token
names, values, and light/dark theme selectors and MUST NOT apply FRED shell layout,
scrolling, selection, or document-root mutations. The package MUST NOT require React,
the iframe SDK, authentication code, application state, or network access.

Generated and accepted token CSS MUST reject `@import` case-insensitively and MUST use
only the reviewed token structure: comments; `:root`, `[data-theme="light"]`, and
`[data-theme="dark"]` rules containing custom-property declarations; the matching
`color-scheme` declaration on each theme selector; and the canonical spectrum-angle
property registration and forced-colors override. Any other selector, ordinary property,
or at-rule MUST fail validation.

#### Scenario: A non-React consumer imports tokens only

- **WHEN** a plain consumer imports the token stylesheet and selects each supported
  `data-theme` value
- **THEN** the existing FRED token variables resolve for both themes without React or
  the font stylesheet being installed or imported implicitly

#### Scenario: A consumer opts into packaged typography

- **WHEN** a consumer explicitly imports the font stylesheet
- **THEN** the declared Geist faces resolve from package-owned files without fetching or
  copying assets from FRED

#### Scenario: A consumer does not opt into fonts

- **WHEN** a consumer imports only the token stylesheet
- **THEN** no font file is loaded and the consumer remains responsible for its chosen
  font policy

#### Scenario: Token CSS attempts to import another stylesheet

- **WHEN** a canonical or packed token stylesheet contains an `@import` using any letter
  casing
- **THEN** generation or archive validation fails instead of relying on an unvalidated
  transitive stylesheet

#### Scenario: Token CSS introduces shell behavior

- **WHEN** a canonical or packed token stylesheet contains an unreviewed selector or an
  ordinary declaration such as `overflow` or `user-select`
- **THEN** generation or archive validation fails before the shell behavior can enter the
  package

### Requirement: Every archive is complete and bounded

Each generated package tarball SHALL contain every file required by its declared public
exports, including transitive CSS, fonts, images or icons when referenced, package
metadata, the FRED license, and all applicable third-party asset licenses and notices.
Its manifest SHALL expose only documented public entry points and SHALL bound the files
eligible for packing. Generated JavaScript, declarations, and CSS MUST NOT contain FRED
source aliases, repository-relative paths, absolute checkout paths, undeclared runtime
dependencies, `workspace:` references, or local `file:` dependencies.

#### Scenario: The complete design-token archive is checked

- **WHEN** the design-token package is packed and its manifest, file list, exports, and
  CSS references are validated
- **THEN** every exported stylesheet and referenced font is present in the tarball with
  the required license and notice material, and no undeclared file is needed

#### Scenario: A referenced asset is absent

- **WHEN** an exported stylesheet references a missing font, image, or icon
- **THEN** archive validation fails before the package can be accepted or published

#### Scenario: An export escapes the package

- **WHEN** a public export or generated file resolves through a FRED alias, checkout
  path, workspace link, local file dependency, or file outside the tarball
- **THEN** archive validation fails and identifies the invalid reference

#### Scenario: The archive contains an unintended file

- **WHEN** the packed file list contains a file outside the package's bounded public and
  metadata inventory
- **THEN** archive validation fails instead of silently widening the distributable
  artifact

#### Scenario: A packed license is incomplete or modified

- **WHEN** a packed FRED or third-party license differs from its approved complete
  content, including by truncation or modification
- **THEN** archive validation fails even if the remaining text still contains the
  license title, version, or copyright line

### Requirement: Archive validation uses an isolated consumer

Acceptance SHALL install the generated tarball into a neutral consumer located outside
the FRED workspace and SHALL build that consumer using only the installed archive and
its declared registry dependencies. The consumer MUST NOT resolve source files,
dependencies, package-manager links, or workspace links from the FRED checkout.

#### Scenario: A packed archive builds independently

- **WHEN** the neutral consumer is created in an isolated location, installs the
  tarball, imports each documented design-token entry point, and runs its production
  build
- **THEN** installation and build succeed without a sibling FRED checkout, manual asset
  copying, or a link to the producer workspace

#### Scenario: The archive relies on producer state

- **WHEN** the consumer can build only by resolving a source path, dependency, symlink,
  or workspace relationship from the FRED checkout
- **THEN** the isolated-consumer check fails

### Requirement: Browser smoke evidence is local and behavior-based

Archive acceptance SHALL include a real-browser smoke test that is separate from the
dependency-free neutral consumer build and runs against that consumer's staged output.
The smoke test MUST use an already provisioned browser, MUST NOT install or download
dependencies or browsers during execution, and MUST reject asset access to the FRED
checkout and external font services.

#### Scenario: Representative styles resolve in both themes

- **WHEN** the browser loads the staged tokens-only consumer and selects the supported
  light and dark themes
- **THEN** representative computed color, spacing, radius, and typography styles match
  the packaged token values in each theme

#### Scenario: A browser opts into packaged Geist fonts

- **WHEN** a staged consumer explicitly imports the packaged font stylesheet and uses
  its regular and italic Geist faces
- **THEN** the browser reports those faces loaded successfully from package-owned files

#### Scenario: A fresh browser consumes tokens only

- **WHEN** a fresh browser context with no cache or service-worker state loads a staged
  consumer that imports only the token stylesheet
- **THEN** the browser records no font requests

#### Scenario: Browser assets remain local to the staged consumer

- **WHEN** either browser smoke page loads and its requests are recorded
- **THEN** every asset request is served successfully by the local staged consumer, every
  HTTP response is successful, and no request uses a FRED checkout path, a `file:` URL,
  or an external font-service origin

#### Scenario: A browser stylesheet request fails

- **WHEN** either smoke page has a failed stylesheet request or receives an unsuccessful
  HTTP response
- **THEN** browser smoke validation fails rather than accepting partial computed-style
  evidence

#### Scenario: Browser prerequisites are provisioned separately

- **WHEN** package-validation dependencies and the pinned browser have been provisioned
  before the smoke target starts
- **THEN** the smoke target uses those installed prerequisites without performing a
  package installation, browser download, or external network request

### Requirement: CI selection covers every package-validation input

Pull-request validation SHALL select the frontend-package job when the producer
workspace; a consumed canonical component, type, stylesheet, protocol source, or path
validator; the FRED frontend React manifest or lockfile baseline; a packaged Geist or
Material Symbols asset; an applicable license or notice input; an SDK compatibility or
isolated-consumer fixture; or relevant validation orchestration changes. Release
readiness validation SHALL also be selected when a release coordinate contract,
candidate metadata, exact producer-toolchain pin, release-evidence schema, registry
verifier, fixture-transfer helper or metadata, bootstrap-publication helper, release runbook,
dedicated first-release workflow, governing frontend packaging RFC, or release-specific
orchestration changes. It MAY skip that
job for application changes that affect neither package generation nor package/host
compatibility or release validation. Existing frontend selection MUST continue to run
the FRED host, request, path, and proxy regressions when their application inputs change.
Every selected job that executes isolated-consumer validation MUST provision its own exact
consumer prerequisites in a distinct network-capable step before offline tests begin; it MUST
NOT depend on another job's filesystem or introduce network fallback into validation.

#### Scenario: Release readiness provisions its isolated consumers

- **WHEN** the release-readiness job installs producer dependencies and will subsequently run
  consumer-dependent package tests
- **THEN** it provisions the isolated-consumer caches in that job before those tests, after which
  archive installation and validation remain offline

#### Scenario: Fixture transfer inputs change

- **WHEN** a pull request changes fixture-transfer production, verification, evidence,
  workflow-artifact orchestration, or a downstream transferred-archive gate
- **THEN** CI selects both the release-toolchain producer and its application-toolchain receiver
  while unrelated application-only changes retain their existing selection behavior

#### Scenario: The producer workspace changes

- **WHEN** a pull request changes a file in the frontend package producer workspace
- **THEN** CI selects the frontend-package validation job

#### Scenario: Consumed canonical CSS changes

- **WHEN** a pull request changes a canonical FRED stylesheet consumed by token, font,
  shared-base, or component-style generation
- **THEN** CI selects the frontend-package validation job

#### Scenario: A consumed component or type changes

- **WHEN** a pull request changes a canonical component, shared prop or visual type, or
  Sass support file in the UI package allowlist
- **THEN** CI selects the frontend-package validation job

#### Scenario: A canonical protocol or path rule changes

- **WHEN** a pull request changes the maintained protocol source or relative-path rules
  consumed by the SDK and host compatibility checks
- **THEN** CI selects both frontend-package validation and the applicable FRED frontend
  regression checks

#### Scenario: A host compatibility input changes

- **WHEN** a pull request changes the application host page, request adapter, frame/path
  integration, or their compatibility tests
- **THEN** CI selects the FRED frontend regression checks and every declared SDK/host
  compatibility gate affected by that input

#### Scenario: The tested React baseline changes

- **WHEN** a pull request changes the FRED frontend manifest or lockfile entries that
  establish the UI package's tested React or React DOM baseline
- **THEN** CI selects the frontend-package validation job

#### Scenario: A packaged Geist asset changes

- **WHEN** a pull request changes either canonical Geist font binary packaged by the
  design-token member
- **THEN** CI selects the frontend-package validation job

#### Scenario: The packaged Material Symbols asset changes

- **WHEN** a pull request changes the canonical Material Symbols Outlined binary used by
  the UI member
- **THEN** CI selects the frontend-package validation job

#### Scenario: An applicable license input changes

- **WHEN** a pull request changes a license, provenance record, glyph inventory, or
  notice input applicable to a generated archive
- **THEN** CI selects the frontend-package validation job

#### Scenario: Release readiness input changes

- **WHEN** a pull request changes selected release coordinates, package metadata,
  dependency ranges, a toolchain pin, candidate evidence or registry-verification logic,
  release documentation, or the workflow that validates them
- **THEN** CI selects the frontend-package release-readiness and applicable existing
  archive regression jobs

#### Scenario: First-release workflow input changes

- **WHEN** a pull request changes the guarded publication workflow, bootstrap helper, release
  transfer/evidence logic, selected manifest metadata, or its workflow-contract tests
- **THEN** CI selects release readiness and the existing archive, consumer, and compatibility
  regressions without exposing a publication credential to those jobs

#### Scenario: Validation orchestration changes

- **WHEN** a pull request changes a root command, workflow, setup action, build
  configuration, fixture lockfile, or validation script that controls the
  frontend-package or host-compatibility gates
- **THEN** CI selects the affected validation jobs

#### Scenario: An unrelated application file changes

- **WHEN** a pull request changes only application files that are not consumed by or
  responsible for frontend-package, SDK/host compatibility, or release validation
- **THEN** CI may skip the frontend-package job while retaining normal application
  validation

### Requirement: The foundation remains application-agnostic

The design-token artifact and its validation SHALL accept consumers without embedding a
consumer identity, route, backend model, or service endpoint. This slice MUST NOT change
FRED's existing iframe protocol or move authentication, team selection, navigation
authority, or authenticated application requests into a package.

#### Scenario: An arbitrary external application consumes the archive

- **WHEN** a neutral application with no RAGS-specific identity or FRED business types
  installs the design-token tarball
- **THEN** it can use the documented style exports without consumer-specific package or
  host behavior

#### Scenario: Existing hosted applications continue using protocol version 1

- **WHEN** the package foundation is introduced without installing an iframe SDK
- **THEN** the existing protocol-1 host, source-window and origin checks, and host-owned
  bearer handling remain unchanged

### Requirement: The UI archive exposes a reviewed initial component contract

The `@fred/ui` archive SHALL expose named JavaScript and TypeScript declarations for
`Button`, `IconButton`, `Icon`, `TextInput`, and `Spinner`, together with only the prop
and visual types required to use those components. The package MUST NOT expose
`TextArea`, `Checkbox`, `Switch`, `Chip`, `PageEmptyState`, overlays, application
components, or internal source paths in this change.

`Button` and `IconButton` SHALL accept only their implemented `2xs`, `small`, and
`medium` sizes without removing `xs` or any other value from the application-wide
`ComponentSize` type used by other controls.

#### Scenario: A consumer imports every reviewed export

- **WHEN** an external TypeScript application imports each documented component and
  public type from `@fred/ui`
- **THEN** type checking and production bundling succeed without a deep import or a
  FRED source alias

#### Scenario: A consumer requests an unsupported button size

- **WHEN** a consumer assigns `xs` or another unimplemented size to `Button` or
  `IconButton`
- **THEN** TypeScript rejects the value even though other FRED controls may continue to
  use that value through the shared application type

#### Scenario: A deferred component is deep-imported

- **WHEN** a consumer attempts to import a deferred component or an internal generated
  module
- **THEN** the package export map prevents that import from becoming a supported public
  contract

### Requirement: The UI package has one maintained implementation

Package generation SHALL consume an explicit allowlist of the selected canonical
component, type, style, and asset files under `apps/frontend`. Generated intermediates
and package output MAY reproduce those inputs for compilation, but the repository MUST
NOT contain a second manually maintained implementation of a selected component.
Application behavior and supported application call sites MUST remain compatible with
the canonical-source corrections required by the public package.

Before changing a shared icon type or coercion helper, implementation SHALL inventory
static and dynamically supplied icon names and SHALL preserve application behavior by
explicit compatibility handling or reviewed caller changes. A narrower package API MUST
NOT silently remove a supported FRED application behavior.

#### Scenario: A canonical component changes

- **WHEN** an allowlisted canonical component or style is changed and the UI package is
  rebuilt
- **THEN** the archive reflects the change without a matching edit to another maintained
  component source

#### Scenario: Generated output is rebuilt from a clean state

- **WHEN** disposable UI build output is removed and regenerated
- **THEN** all public modules, declarations, and styles are reproduced from the explicit
  canonical-source allowlist

#### Scenario: A dynamic icon caller relies on existing behavior

- **WHEN** the icon inventory finds a caller that supplies an icon name dynamically
- **THEN** implementation records how that value is validated or adapted and verifies
  the FRED caller before narrowing any shared application type

### Requirement: The UI package externalizes its React runtime

The UI package SHALL export ESM JavaScript, TypeScript declarations, and a separate
`./styles.css` entry point. It SHALL declare React `^19.2.4`, React DOM `^19.2.4`, and a
tested compatible `@fred/design-tokens` version as peer requirements. The build MUST
externalize `react`, `react-dom`, all of their subpaths, and the production and
development JSX runtimes, and MUST retain evidence from the actual build graph that no
React runtime module was bundled.

The archive MUST NOT declare a runtime dependency on application state, routing,
authentication, translations, backend models, the iframe SDK, or a specific external
application.

#### Scenario: A consumer supplies the supported peers

- **WHEN** an isolated React application installs both FRED tarballs and compatible
  React and React DOM peers
- **THEN** every UI export resolves against the consumer's React runtime and the
  consumer has one React installation in its resolved graph

#### Scenario: A React or JSX subpath enters the bundle

- **WHEN** build evidence reports that `react`, `react-dom`, or one of their subpaths or
  JSX runtimes was included as an internal bundled module
- **THEN** UI package validation fails even if peer dependencies are declared

#### Scenario: A public artifact contains an undeclared module reference

- **WHEN** generated JavaScript or declarations reference a bare module outside the
  approved peer contract
- **THEN** archive validation fails and identifies that module reference

### Requirement: The public component corrections preserve accessible native behavior

The packaged components and their canonical FRED implementations SHALL provide the
following reviewed behavior:

- `Button` and `IconButton` retain native button props and behavior;
- `IconButton` combines a caller `className` with all generated visual classes, exposes
  a visible keyboard focus indicator, and remains disabled and busy while loading;
- `Icon` is decorative by default and supports an explicit caller-owned accessible name
  when informative without deriving user-facing text from a glyph identifier;
- `TextInput` preserves caller refs, event handlers, IDs, and native input props; its
  visible label targets the effective input ID, and its error or help text is associated
  with the input while an error sets the native accessibility state;
- controlled and uncontrolled `TextInput` character counts reflect the current value
  rather than stringifying an absent value; and
- `Spinner` accepts caller-supplied status text while retaining its existing `Loading`
  default and its label-free decorative behavior.

#### Scenario: An IconButton receives a caller class

- **WHEN** a consumer renders `IconButton` with `className`
- **THEN** the button retains the caller class and the generated size, color, and variant
  classes so both caller and component styling remain effective

#### Scenario: A keyboard user focuses an IconButton

- **WHEN** keyboard navigation moves focus to an enabled `IconButton`
- **THEN** a visible focus indicator is rendered without requiring pointer interaction

#### Scenario: An icon is decorative

- **WHEN** an icon is rendered inside a labelled button or other labelled control
- **THEN** the icon contributes no duplicate text or glyph name to the control's
  accessible name

#### Scenario: An icon is informative

- **WHEN** a consumer explicitly supplies an accessible name for a standalone
  informative icon
- **THEN** assistive technology receives that caller-owned name

#### Scenario: TextInput uses a caller ID and ref

- **WHEN** a consumer supplies an input ID, ref, native event handlers, and other native
  attributes
- **THEN** the visible label targets that ID, the ref targets the input, the handlers
  run normally, and the native attributes remain effective

#### Scenario: TextInput reports an error

- **WHEN** a non-disabled `TextInput` receives an error message
- **THEN** the input is marked invalid, its accessible description includes that error,
  and the documented error styling is visible

#### Scenario: Compact TextInput retains its description

- **WHEN** a compact `TextInput` receives help or error text that is visually omitted
- **THEN** the input's accessible description still references that caller-visible
  contract text

#### Scenario: TextInput counts an uncontrolled value

- **WHEN** a consumer uses `defaultValue` and `maxLength` without a controlled `value`
- **THEN** the displayed count begins with the actual default value length and follows
  subsequent native edits

#### Scenario: An uncontrolled TextInput is reset by its form

- **WHEN** a changed uncontrolled `TextInput` participates in a successful native form
  reset, including when the form's reset handler updates parent React state and causes
  an ordinary rerender
- **THEN** the input returns to its native default value and the displayed count reflects
  that actual reset value without the rerender canceling synchronization

#### Scenario: A TextInput form reset is canceled

- **WHEN** a consumer cancels the native reset event for a form containing an
  uncontrolled `TextInput`
- **THEN** the input value and displayed count both remain unchanged

#### Scenario: Spinner text is customized

- **WHEN** a non-decorative `Spinner` receives consumer-supplied status text
- **THEN** it exposes that text as its accessible status name, while an omitted value
  continues to expose `Loading`

### Requirement: The UI archive owns a complete Outlined icon contract

The initial UI package SHALL support only Material Symbols Outlined. Every public icon
name MUST be demonstrated to exist in the packed canonical font. The exact origin,
approved SHA-256 hash, complete applicable license, and required notices for that font
MUST be established before the archive can pass; implementation MUST NOT infer missing
provenance or silently replace the canonical binary.

Rounded, Sharp, custom SVG, absolute `/images/icons` lookup, and remote font-service
behavior MUST NOT be part of the public archive.

#### Scenario: The canonical font provenance is unresolved

- **WHEN** the exact source or redistribution material for the canonical Outlined font
  cannot be established
- **THEN** the UI archive acceptance task remains blocked and no substitute asset or
  guessed notice is accepted

#### Scenario: A declared glyph is unsupported

- **WHEN** a public icon name cannot be resolved from the packed Outlined font
- **THEN** generation or archive validation fails before that icon contract is accepted

#### Scenario: The font or its license is changed

- **WHEN** the packed font, complete approved license, or required notice content differs
  from its recorded input or hash
- **THEN** archive validation fails, including for a truncated or otherwise plausible
  license text

#### Scenario: A consumer renders a supported icon

- **WHEN** an isolated consumer renders each representative public icon state
- **THEN** the expected glyph loads from the package-owned Outlined font without a FRED
  path or external font service

### Requirement: UI styles are explicit, scoped, and token-based

Importing `@fred/ui/styles.css` SHALL provide every style and asset required by the
public components. Shared base rules SHALL be scoped to a consumer-owned `.fred-ui`
root, and component selectors SHALL remain private implementation details. The
stylesheet MUST NOT import another stylesheet, set a theme, load Geist, or modify
`html`, `body`, document scrolling, selection, or other shell-wide behavior.

The components SHALL consume the existing `@fred/design-tokens` variable contract.
Consumers SHALL import token CSS explicitly and MAY import the existing separate Geist
stylesheet; importing UI styles MUST NOT make Geist mandatory or duplicate its files.

#### Scenario: A consumer opts into the UI root

- **WHEN** a consumer imports token and UI styles and renders the components beneath
  `.fred-ui`
- **THEN** their box model, component styles, light/dark token values, and package-owned
  icon font resolve without relying on FRED global CSS

#### Scenario: A consumer omits Geist

- **WHEN** a fresh consumer imports token and UI styles but not the token package's
  optional font stylesheet
- **THEN** the components use the token typography contract with the consumer's fallback
  font policy and make no Geist request

#### Scenario: UI CSS introduces shell behavior

- **WHEN** generated or packed UI CSS contains an unscoped base selector, a document
  selector, an import, an external URL, or a shell layout or selection mutation
- **THEN** validation fails before the stylesheet is accepted

#### Scenario: A functional selector only appears scoped by text

- **WHEN** a packed selector mentions a generated class only inside a negation or mixes
  a generated class with an outside branch of a functional pseudo-class
- **THEN** structural selector validation rejects it because every matched subject is
  not contained within the permitted component or `.fred-ui` scope

#### Scenario: UI CSS references an absent token

- **WHEN** generated or packed UI CSS references a custom property that is declared in
  neither the UI stylesheet nor the canonical design-token stylesheets
- **THEN** validation fails before a consumer can receive an unresolved visual state

### Requirement: The UI archive has package-specific completeness evidence

Acceptance of the actual `npm pack` UI tarball SHALL validate its exact export map and
file inventory; JavaScript, declaration, and stylesheet reference closure; approved
peer contract; source-path and workspace independence; complete assets and license
material; CSS safety; and React externalization evidence. The existing design-token
archive and all of its positive and negative acceptance cases MUST continue to pass
unchanged in meaning.

#### Scenario: The complete UI archive is checked

- **WHEN** the UI workspace member is built, packed, and validated
- **THEN** every documented JavaScript, declaration, and stylesheet export plus every
  transitive module, style, font, license, and notice is present and bounded inside the
  archive

#### Scenario: A generated reference is missing or escapes

- **WHEN** JavaScript, declarations, or CSS resolve a missing file, an undeclared bare
  module, a source alias, a checkout path, or a path outside the archive
- **THEN** archive validation fails and identifies the invalid reference

#### Scenario: A runtime import resolves only to a declaration

- **WHEN** packed JavaScript imports a relative path for which only a TypeScript
  declaration exists
- **THEN** archive validation fails because runtime references must resolve to executable
  packed modules while valid declaration references resolve under declaration rules

#### Scenario: Existing token validation runs with the UI package

- **WHEN** the producer's complete validation suite is run after adding the UI member
- **THEN** the design-token generator, archive mutations, isolated neutral consumer,
  theme checks, optional Geist checks, and local-only asset checks retain their existing
  guarantees

### Requirement: An isolated React consumer proves both archives

Acceptance SHALL stage a domain-neutral React consumer outside the FRED checkout,
install the actual design-token and UI tarballs, type-check every public export, and
produce a production build using only the archives and separately provisioned,
lockfile-pinned registry dependencies. Offline validation MUST NOT use FRED source
files, workspace links, local package links, or dependency resolution from the producer
checkout.

Dependency provisioning MAY download only lockfile-pinned consumer dependencies into a
dedicated cache before validation, and browser provisioning MAY install the required
pinned browser separately. Offline validation MAY invoke the package manager to install
the two generated tarballs and pinned consumer dependencies from that prepared cache
into a fresh isolated consumer. It MUST NOT fetch from the network, resolve packages
from FRED's installed dependency tree, use workspace or local-package links, or
bootstrap a missing browser.

Missing cached packages or browser prerequisites MUST cause an actionable failure.
After the isolated consumer has been installed and built, browser smoke execution SHALL
perform no dependency installation and MAY use the network only for its loopback smoke
server traffic.

#### Scenario: Both archives build independently

- **WHEN** the staged consumer installs both tarballs offline and imports every public UI
  and stylesheet entry point
- **THEN** type checking and production building succeed with one consumer-owned React
  runtime and no path or link to FRED

#### Scenario: Offline validation relies on producer state

- **WHEN** installation, type checking, or building can succeed only through a workspace
  package, producer dependency tree, source path, symlink, or network fetch
- **THEN** isolated-consumer validation fails

#### Scenario: Prerequisites have not been provisioned

- **WHEN** the required lockfile-pinned registry packages or browser are absent at the
  start of offline validation
- **THEN** validation fails with an actionable prerequisite error without attempting a
  network fetch, using FRED's installed dependency tree, or bootstrapping a browser

#### Scenario: The isolated consumer is installed from the prepared cache

- **WHEN** offline validation creates a fresh consumer and invokes its package manager
- **THEN** the two generated tarballs and every lockfile-pinned consumer dependency are
  installed only from the dedicated prepared cache without network or FRED workspace
  resolution

#### Scenario: Browser smoke execution starts

- **WHEN** the built isolated consumer and provisioned browser are available
- **THEN** smoke execution starts without invoking dependency installation or browser
  provisioning

### Requirement: UI browser evidence covers behavior and local assets

The isolated React consumer SHALL be exercised in a real, separately provisioned
browser. It MUST render every public component in light and dark themes and verify
representative computed styles, keyboard activation, accessible names, disabled,
loading, and error behavior, optional Geist loading, Material glyph rendering, and
successful package-local asset responses. Fresh browser contexts MUST reject failed or
unsuccessful resources, non-loopback requests, FRED checkout paths, `file:` URLs, and
external font services.

#### Scenario: Every component renders in both themes

- **WHEN** the browser switches the isolated consumer between light and dark token
  themes
- **THEN** each public component remains usable and representative foreground,
  background, border, focus, spacing, and typography styles resolve to the selected
  packaged tokens

#### Scenario: Keyboard interactions use native behavior

- **WHEN** a browser user tabs through the component fixture and activates its buttons
  with Enter or Space
- **THEN** focus order, visible focus, click handling, disabled suppression, and loading
  suppression match the documented native component behavior

#### Scenario: Neutral tonal IconButtons expose interaction state

- **WHEN** the browser hovers and presses tonal IconButtons using the `on-surface` and
  `on-surface-retreat` public colors
- **THEN** each state layer resolves to distinct non-transparent packaged token values

#### Scenario: Accessible names and errors are inspected

- **WHEN** the browser queries the fixture by button, textbox, and status roles
- **THEN** caller-owned names, decorative icons, informative icons, spinner text, and
  TextInput error descriptions are exposed without duplicate glyph text

#### Scenario: Optional and required fonts remain distinct

- **WHEN** fresh browser contexts load a UI page without Geist and another page that
  explicitly imports the token font stylesheet
- **THEN** Material glyphs load locally on the UI page, the first page makes no Geist
  request, and the second page loads packaged Geist successfully

#### Scenario: A browser asset is not local and successful

- **WHEN** a component page requests a checkout path, external font service, `file:` URL,
  non-loopback resource, missing stylesheet or font, or unsuccessful HTTP response
- **THEN** browser validation fails rather than accepting partial visual evidence

#### Scenario: UI styles are removed

- **WHEN** the consumer builds or renders without the explicit `@fred/ui/styles.css`
  import
- **THEN** validation demonstrates that the JavaScript export alone does not conceal an
  implicit stylesheet or asset dependency

### Requirement: The UI foundation remains application-agnostic

The UI archive and its fixtures SHALL contain no RAGS identity, FRED route, backend
model, service endpoint, translation catalog, application state, iframe protocol, or
authentication behavior. This change MUST NOT alter the existing protocol-1 iframe
contract or move host-owned bearer, authorization, team, or navigation responsibilities
into the package.

#### Scenario: A neutral React application consumes the UI archive

- **WHEN** an application with no FRED or RAGS business model installs the two archives
- **THEN** it can render and interact with every public component using only
  caller-supplied content, handlers, accessible names, theme selection, and peers

#### Scenario: Existing hosted applications remain unchanged

- **WHEN** the UI package foundation is added without iframe SDK or adoption work
- **THEN** protocol version 1, source-window and origin validation, host-owned bearer
  handling, and application registration behavior remain unchanged

### Requirement: The iframe SDK exposes a framework-independent public contract

The `@fred/iframe-sdk` archive SHALL expose its child client from `.` and the shared
protocol `"1"` wire contract from `./protocol` as ESM JavaScript and closed TypeScript
declarations. It MUST NOT depend on React, React DOM, `@fred/ui`,
`@fred/design-tokens`, FRED application state, routing libraries, Keycloak, backend
models, or consumer-specific code. Undocumented deep imports MUST remain blocked.

#### Scenario: A neutral TypeScript consumer imports both entry points

- **WHEN** an application with no framework dependency imports the documented client
  API and protocol types from the packed archive
- **THEN** type checking and production bundling succeed without React, another FRED
  package, a deep import, or access to FRED source

#### Scenario: A consumer requests an internal module

- **WHEN** a consumer attempts to import a generated or internal SDK module
- **THEN** the package export map prevents that module from becoming public API

### Requirement: One authoritative source defines protocol 1

FRED and the generated package SHALL consume one maintained protocol source for the
existing `fred:ready`, `fred:context`, `fred:route`, `fred:navigate`, `fred:open-chat`,
`fred:request`, `fred:response`, and `fred:response-error` messages. The serialized
field names, required values, and existing default normalization MUST remain compatible
with protocol `"1"`. Package generation MUST NOT introduce a second maintained wire
definition.

The protocol entry point SHALL expose the version, message and context types, request
methods and limits, pure message parsers, protected-header predicate, and relative-path
validator needed by the host and child. Host-only catalog, frame-target, route-target,
session-resolution, bearer, and fetch implementations MUST remain outside it.

#### Scenario: The updated host receives a legacy client message

- **WHEN** a raw protocol-`"1"` client sends any currently supported frame-to-host
  serialized shape
- **THEN** the host preserves its current parsing, defaults, routing, request, and error
  behavior

#### Scenario: The new SDK connects to the protocol-1 host

- **WHEN** the packed SDK sends protocol-`"1"` messages to the existing host behavior
- **THEN** the host accepts them without a protocol extension or compatibility adapter

#### Scenario: Generated protocol output diverges

- **WHEN** the host and packed protocol entry point are no longer derived from the same
  canonical source and reviewed build graph
- **THEN** generation or compatibility validation fails before the archive is accepted

### Requirement: Connection admission is explicit and bounded

The client SHALL require an explicit HTTP(S) host origin and expected application ID.
It SHALL install its listener before sending `fred:ready`, post only to that exact
origin and `window.parent`, and accept messages only when `event.origin` equals the
configured origin and `event.source` equals `window.parent`. A valid initial
`fred:context` MUST carry protocol version `"1"`, the expected application ID, and the
complete cloneable team, route, and locale context before the client becomes connected.

`connect()` SHALL send `fred:ready` immediately and retry at a fixed bounded cadence
until it connects or reaches a default 10-second connection deadline. Concurrent calls
SHALL share the same connection lifecycle. A missing parent, malformed context,
unsupported protocol, application-ID mismatch, deadline, or disposal MUST fail
actionably rather than becoming a silent connection.

#### Scenario: A configured child completes the handshake

- **WHEN** the expected parent answers a ready announcement from the configured origin
  with a valid matching context
- **THEN** connection resolves once with that context and handshake retries stop

#### Scenario: A ready announcement races host setup

- **WHEN** the first ready announcement is not observed but the host becomes available
  before the connection deadline
- **THEN** a bounded retry permits connection without creating a second client lifecycle

#### Scenario: A message comes from the wrong source or origin

- **WHEN** a structurally valid host message comes from another window or a different
  origin
- **THEN** the client ignores it without connecting, navigating, or settling a request

#### Scenario: Context names another application

- **WHEN** the configured parent sends a context whose application ID differs from the
  client's expected identity
- **THEN** connection fails with an application-mismatch error and no operational host
  message is accepted

#### Scenario: The host never completes the handshake

- **WHEN** no valid matching context arrives within the connection deadline
- **THEN** connection rejects, retries and timers stop, and operational methods remain
  unavailable

### Requirement: Context, route, and navigation APIs preserve host ownership

The connected client SHALL expose the accepted initial context and route-event
subscriptions. It SHALL deliver each accepted `fred:route` message exactly once to each
subscriber that is current when the message is handled. It MUST NOT deduplicate accepted
route messages solely because their `subPath` equals a previously delivered value. It
SHALL send only relative `fred:navigate` intents with explicit
replace semantics and `fred:open-chat` with a string session candidate or `null`.
Relative path validation MUST reject absolute, schemed, fragmented, malformed,
backslash, and single- or multiply-encoded traversal paths before posting while the
host remains authoritative.

The SDK MUST NOT inspect or mutate the parent DOM, select a FRED route outside the
application subtree, resolve a chat destination, infer team identity, or add theme or
live-locale context behavior in this slice.

#### Scenario: The host changes the application route

- **WHEN** a connected client receives a valid `fred:route` message from its accepted
  parent and origin
- **THEN** every current route subscriber receives the host-owned sub-path once

#### Scenario: Navigation returns to a previously delivered route

- **WHEN** the host sends route A, the child requests navigation to B, and the host later
  sends route A again
- **THEN** every subscriber current for each host message observes A and then A again,
  with neither accepted route event suppressed by sub-path deduplication

#### Scenario: A consumer requests application navigation

- **WHEN** a connected consumer supplies a valid relative path and replace choice
- **THEN** the client sends the existing normalized `fred:navigate` shape without
  choosing the resulting FRED route

#### Scenario: A consumer opens chat with no trusted destination

- **WHEN** a consumer calls open-chat with an optional session candidate
- **THEN** the client sends only that candidate and the host retains all destination and
  authorization decisions

#### Scenario: A path attempts to escape

- **WHEN** a consumer supplies an absolute, schemed, fragmented, malformed, or
  traversing path to navigation or request
- **THEN** the client rejects it locally and sends no message

### Requirement: Request correlation, limits, cancellation, and disposal are deterministic

The client SHALL generate unique protocol-`"1"` request IDs no longer than 128
characters, permit only `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE`, serialize
at most 32 ordinary string headers, and allow no more than 16 pending requests. It MUST
reject protected headers case-insensitively before posting. Requests issued before
connection or beyond the pending bound MUST fail locally.

Replies SHALL correlate by request ID and may arrive out of order. The first valid
reply SHALL settle and remove its pending request; duplicate, unknown, canceled, timed
out, disposed, or otherwise late replies MUST be ignored. Requests SHALL have a
default 30-second local deadline and accept caller `AbortSignal` cancellation. Timeout
or abort releases local state but MUST NOT claim to cancel host fetch or remote work and
MUST NOT automatically retry a mutation.

`dispose()` SHALL be idempotent, remove listeners, stop connection/request timers,
reject unsettled work, clear subscribers, and make subsequent operations fail. A new
frame lifecycle SHALL require a new client.

#### Scenario: Responses arrive out of order

- **WHEN** two accepted requests receive valid replies in the reverse order
- **THEN** each promise settles exactly once with the reply carrying its generated ID

#### Scenario: Pending capacity is exhausted

- **WHEN** 16 requests remain pending and a consumer attempts another request
- **THEN** the additional request fails locally without sending a seventeenth message

#### Scenario: A request times out or is aborted

- **WHEN** its local deadline expires or its caller signal aborts before a reply
- **THEN** the promise rejects predictably, its pending slot is released, and no remote
  cancellation or automatic retry is claimed

#### Scenario: A duplicate or late reply arrives

- **WHEN** a reply arrives after its request settled, timed out, was canceled, or the
  client was disposed
- **THEN** the client ignores it without settling another request or restoring state

#### Scenario: The client is disposed with pending work

- **WHEN** disposal occurs during connection or one or more requests
- **THEN** every unsettled promise rejects, all local resources are released, and a
  later message from the old frame lifecycle has no effect

### Requirement: The request API describes the buffered protocol accurately

The public request API SHALL accept only the protocol's string-or-null body and SHALL
reconstruct a browser `Response` from a successful `fred:response`. HTTP error statuses
including 401, 403, and 5xx MUST resolve as Responses whose status and headers remain
inspectable; `fred:response-error` and local transport failures MUST reject separately.
HEAD and status 204, 205, or 304 responses MUST be reconstructed without a body so
bodyless replies do not throw during construction.

Documentation MUST identify this as buffered text/JSON transport rather than full Fetch
equivalence. It MUST NOT promise binary bodies, multipart uploads, response streaming,
SSE, remote cancellation, detailed host transport reasons, or automatic retry.

#### Scenario: A successful JSON response arrives

- **WHEN** the host returns a successful status, headers, and buffered JSON text
- **THEN** the resolved Response exposes the same status and headers and its text or JSON
  reader consumes the buffered body

#### Scenario: The application service returns an HTTP error

- **WHEN** the host returns 401, 403, or a 5xx `fred:response`
- **THEN** the request resolves with that non-OK Response rather than becoming an SDK
  transport exception

#### Scenario: The host reports a transport failure

- **WHEN** the host sends `fred:response-error` for a pending request
- **THEN** the request rejects with a generic transport error that does not invent or
  expose a host-side reason

#### Scenario: A bodyless response arrives

- **WHEN** a HEAD request or 204, 205, or 304 response carries the host's buffered empty
  string
- **THEN** the SDK constructs a valid bodyless Response while preserving status and
  headers

### Requirement: FRED remains the authority for hosting and authenticated requests

The extraction SHALL preserve FRED's authorized application lookup, configured frame
target, exact source/origin checks, 15-second host handshake deadline, 16-request host
concurrency bound, duplicate-ID refusal, route and open-chat resolution, team/frame
teardown, protected-header enforcement, bearer injection, pre-request refresh, single
401 retry, and logout-only-on-refresh-failure behavior. No bearer, Keycloak object,
host state, service upstream, or authorization result MAY enter SDK context or messages.

#### Scenario: A frame or team lifecycle changes

- **WHEN** the hosted application, frame target, or selected team is replaced or the
  host unmounts
- **THEN** the old host listener is removed, its in-flight fetches are aborted, and old
  frame messages or replies cannot affect the new lifecycle

#### Scenario: A protected header bypasses local validation

- **WHEN** a legacy or hostile client sends a protected request header directly
- **THEN** the host still rejects it without forwarding the caller's value

#### Scenario: The application service returns 401

- **WHEN** the host request adapter receives an application-service 401
- **THEN** FRED preserves its one refresh/retry policy and logs out only when refresh
  itself fails, independently of SDK behavior

#### Scenario: The packed SDK exercises the production host handler

- **WHEN** the actual generated SDK tarball connects to the production message handler used by
  FRED's host page
- **THEN** ready/context, route delivery, navigation, open-chat, request correlation, HTTP and
  transport outcomes, pending limits, and stale frame/team teardown work without a protocol
  adapter or loss of host authority

#### Scenario: Host routing returns to a prior route through the packed SDK

- **WHEN** the production host sends route A, the packed SDK sends child navigation to B, and the
  production host later sends route A
- **THEN** the SDK delivers both accepted A events to current subscribers while request responses
  remain deduplicated by request ID

### Requirement: The iframe SDK archive is complete and independently consumable

Acceptance of the actual `npm pack` SDK tarball SHALL validate its exact `.` and
`./protocol` export map, declarations, executable-module closure, file inventory,
metadata, complete FRED license, dependency absence, canonical-source/build evidence,
and freedom from checkout paths, aliases, links, local dependency protocols, bundled
Node code, and unrelated FRED package or application code. Runtime imports and runtime
export conditions MUST resolve to executable packed modules. Declaration references and
`types` export conditions MAY resolve to valid packed `.d.ts` files and MUST be checked
with declaration-aware resolution independently of runtime resolution. A declaration-only
target MUST NOT satisfy a runtime reference. Existing design-token and UI positive and
negative archive guarantees MUST continue unchanged.

Reference inspection SHALL use the TypeScript compiler API to parse JavaScript and declaration
syntax and inspect static imports, re-exports, dynamic imports, declaration import types, and
applicable reference directives. Comments MUST NOT hide a reference. Literal strings and
no-substitution template literals MUST be inspected. A computed runtime import or malformed module
syntax MUST fail validation. Build-graph evidence SHALL use the same syntax-aware reference
inspection rather than a less complete textual scan.

Every packed executable module SHALL also pass a parse-only native ESM grammar check without being
imported or executed. The check MUST reject grammar-invalid JavaScript that a permissive TypeScript
AST can still represent, including top-level `return` and TypeScript-only annotations in `.js`.

Runtime relative references SHALL resolve exactly as written to executable packed JavaScript.
Validation MUST NOT infer an omitted extension or fall back from a directory to `index.js` because
native ESM consumption does not perform those substitutions. Declaration resolution SHALL remain
separate and declaration-aware.

A lockfile-pinned neutral JavaScript/TypeScript consumer SHALL install the actual SDK
tarball in a fresh OS temporary directory outside FRED, type-check both public entry
points, and produce a browser build without React or any other FRED package.

#### Scenario: The actual SDK archive is validated

- **WHEN** the SDK workspace member is generated, packed, and checked
- **THEN** every runtime reference resolves to executable packed JavaScript, every
  declaration reference resolves to a valid packed declaration, and the package has no
  undeclared or framework dependency

#### Scenario: Runtime references resolve through executable modules

- **WHEN** a valid runtime entry point or executable packed module imports or exports
  another runtime module
- **THEN** archive validation resolves the reference through executable files contained
  in the exact packed archive

#### Scenario: Comments surround a static module reference

- **WHEN** a runtime or declaration import places comments between its syntax tokens and its
  literal module specifier
- **THEN** syntax-aware validation still inspects and resolves that reference through the
  applicable runtime or declaration path

#### Scenario: A dynamic import uses a literal template

- **WHEN** runtime JavaScript dynamically imports a no-substitution template literal
- **THEN** archive validation resolves its exact target as an executable packed module

#### Scenario: A runtime import is computed

- **WHEN** runtime JavaScript calls `import()` with an identifier, expression, or interpolated
  template rather than a statically reviewable module literal
- **THEN** SDK archive validation fails instead of accepting an unknown runtime dependency

#### Scenario: Packed module syntax is malformed

- **WHEN** an executable or declaration module cannot be parsed without syntax diagnostics
- **THEN** SDK archive validation fails before accepting its reference graph

#### Scenario: A runtime module is not valid native ESM grammar

- **WHEN** a packed executable contains top-level `return`, TypeScript-only annotations, or another
  construct that the TypeScript AST accepts but native ESM grammar rejects
- **THEN** parse-only native validation rejects the archive without executing the module

#### Scenario: A runtime import omits its executable extension

- **WHEN** runtime JavaScript imports `./protocol` while only `./protocol.js` is packed
- **THEN** archive validation fails and a native ESM loading check confirms the entry point is not
  consumable as written

#### Scenario: A runtime import names a packed directory

- **WHEN** runtime JavaScript names a directory whose `index.js` could be found only by fallback
- **THEN** archive validation fails rather than treating the directory as an executable target

#### Scenario: A runtime reference has only a declaration target

- **WHEN** a runtime import or runtime export condition resolves only to a packed `.d.ts`
  file or similarly named declaration
- **THEN** SDK archive validation fails even though TypeScript declaration resolution
  could find that target

#### Scenario: Declaration references resolve through packed declarations

- **WHEN** a valid declaration import, reference, or `types` export condition names a
  packed declaration target
- **THEN** archive validation resolves it through the applicable `.d.ts` file without
  requiring that type-only target to be executable

#### Scenario: Declaration import types remain declaration-aware

- **WHEN** a declaration contains a commented or ordinary `import("./types.js").Name` reference
- **THEN** syntax-aware validation resolves it using the packed declaration graph without applying
  runtime executable-target rules

#### Scenario: A declaration reference is missing or invalid

- **WHEN** a declaration import, reference, or `types` export condition has no valid
  packed `.d.ts` target
- **THEN** SDK archive validation fails even if similarly named executable JavaScript is
  present

#### Scenario: An archive reference is missing or escapes

- **WHEN** JavaScript, declarations, or exports reference a missing, aliased, absolute,
  checkout-relative, undeclared, or outside-package target
- **THEN** SDK archive validation fails before consumption

#### Scenario: The tarball is consumed outside FRED

- **WHEN** the neutral consumer installs the SDK tarball and pinned tooling offline,
  imports both entry points, type-checks, and builds
- **THEN** it succeeds without FRED source, FRED dependencies, a workspace or local
  package link, or React

#### Scenario: Existing package validation runs with the SDK

- **WHEN** the producer's complete suite runs after adding the SDK member
- **THEN** every existing token and UI generation, archive mutation, isolated-consumer,
  CSS, asset, license, peer, and browser assertion retains its meaning

### Requirement: Provisioning is separate from offline SDK validation

Dependency provisioning MAY download only lockfile-pinned neutral-consumer dependencies
into a dedicated cache, and browser provisioning MAY install the pinned browser before
validation. Offline consumer validation MAY install the actual SDK tarball and pinned
dependencies from that cache, but MUST NOT fetch from the network, resolve FRED's
installed dependency tree, or bootstrap a missing browser. Browser smoke execution
MUST perform no dependency installation or browser provisioning.

#### Scenario: Offline prerequisites are available

- **WHEN** the dedicated cache and pinned browser were provisioned separately
- **THEN** fresh consumer installation, type checking, production build, and browser
  smoke complete without an external network request

#### Scenario: A cache or browser prerequisite is missing

- **WHEN** offline validation starts without a required cached package or browser
- **THEN** it fails with the applicable provisioning command and does not fall back to
  the network or FRED dependencies

### Requirement: Browser evidence uses a real cross-origin iframe

The packed SDK SHALL be exercised in a real iframe whose loopback child origin differs
from the loopback host origin. Browser checks SHALL cover handshake and context,
host-to-child route events, child navigation and open-chat intents, request/reply
correlation, successful and HTTP-error Responses, transport failures, bodyless
Responses, malformed messages, wrong origins and windows, capacity, deadlines,
disposal, late responses, and host frame/team lifecycle behavior. Every resource
response MUST succeed locally, and non-loopback, `file:`, external-service, and FRED
checkout requests MUST fail validation.

The host fixture SHALL validate its host, application, and attacker configuration as three
distinct canonical `http://127.0.0.1:<port>` origins before assigning either iframe's `src`.
Credentials, missing or invalid ports, other schemes or hosts, protocol-relative input, and any
path, query, fragment, malformed, or non-canonical form MUST be rejected. Initial and replacement
destinations SHALL be constructed from the fixed permitted scheme, host, fixture paths, validated
numeric ports, and URL/search-parameter APIs. These fixture-only constraints MUST NOT narrow the
production SDK's documented HTTP(S) origin support.

Readonly context and route declaration checks SHALL be compiled from a dedicated typecheck-only
fixture that is not reachable from a browser entry. Both negative assignments MUST use consumed
`@ts-expect-error` directives so either property becoming writable fails isolated type checking.

#### Scenario: Distinct origins complete the protocol lifecycle

- **WHEN** the isolated child runs in an iframe on a different loopback origin from its
  host fixture
- **THEN** the packed client connects and exercises context, routes, intents, and
  buffered requests using only exact-origin `postMessage`

#### Scenario: Valid dynamic fixture origins are constructed safely

- **WHEN** the harness supplies three distinct dynamically allocated loopback ports
- **THEN** the host, child, and attacker retain distinct origins and initial and replacement frames
  navigate only to their fixed paths under the validated origins

#### Scenario: A fixture origin is unsafe or ambiguous

- **WHEN** either configured origin uses an executable, file, unsupported, or protocol-relative
  scheme; an external or misleading host; credentials; an invalid port; an unexpected URL
  component; a malformed form; or duplicates another fixture origin
- **THEN** configuration fails before either iframe receives a navigation destination

#### Scenario: Readonly declarations are checked without browser code

- **WHEN** the isolated consumer type-checks and builds its browser entries
- **THEN** both readonly mutations are rejected by TypeScript while their typecheck-only fixture is
  absent from the browser runtime graph

#### Scenario: Another window impersonates the parent or child

- **WHEN** a sibling, popup, stale frame, or wrong-origin document sends an otherwise
  valid protocol message
- **THEN** the receiving client or host ignores it because both source and origin do not
  match the configured lifecycle

#### Scenario: Browser resources leave the isolated fixture

- **WHEN** either host or child requests a non-loopback resource, a FRED checkout path,
  a file URL, or an unsuccessful resource
- **THEN** browser validation fails rather than accepting partial protocol evidence

### Requirement: The iframe SDK remains application-agnostic

The SDK, protocol source, fixtures, and archive SHALL contain no RAGS identity, consumer
route, business model, service endpoint, token, registry assumption, or
application-specific branch. Consumer values SHALL enter only through documented
configuration, context, paths, bodies, headers, and handlers. This slice MUST NOT
change protocol version `"1"`, application registration, authorization policy, or
deployment ownership.

#### Scenario: A different external application uses the SDK

- **WHEN** a neutral consumer supplies a different valid application ID, host origin,
  route, and ordinary request data
- **THEN** the same packed client operates without package or host changes specific to
  that consumer

### Requirement: Release coordinates and metadata are explicit

The release-readiness process SHALL consume an explicitly selected contract for the
independently versioned design-token, UI, and iframe SDK packages. The contract MUST
state the expected package names, exact versions, dependency and peer ranges, release
metadata, and intended dist-tag; validation MUST compare candidate contents with that
contract rather than accepting metadata declared by an archive as its own expectation.

The producer workspace root MUST remain `private: true`, MUST NOT be a release
candidate, and MUST be distinguished from the publication eligibility and configuration
of each member package. Published member manifests MUST agree with the selected contract,
MUST contain no `workspace:`, `file:`, `link:`, `git+file:`, directory, source-checkout, or other local
dependency reference, and MUST preserve the existing exports, asset, license, notice,
CSS, React-peer, and protocol contracts.

The private producer lockfile MAY contain npm-generated `link: true` entries only for the
exact members declared by the root workspace manifest. Each such entry MUST resolve to
its declared member directory within the producer workspace. The lockfile MUST reject an
undeclared linked package, a member-name mismatch, an escaping target, or any other link
that is not npm's representation of an explicitly declared producer member.

The selected coordinates SHALL be `@fred-oss/design-tokens@0.1.0-alpha.1`,
`@fred-oss/ui@0.1.0-alpha.1`, and `@fred-oss/iframe-sdk@0.1.0-alpha.1` on
`https://registry.npmjs.org/` with public access and initial `next` dist-tag. Bootstrap
account `marc.fawaz` SHALL be recorded separately from the future Trusted Publishing
workflow identity, together with the maintainer-supplied confirmation that it has the
`fred-oss` organization-owner role. Package API, SDK protocol, release, and enduring npm
publishing ownership SHALL each be explicitly assigned to `marc.fawaz`, and subsequent releases
SHALL use the selected direct Trusted Publishing policy with GitHub environment approval. The
distinct GitHub reviewer identity `marcfawaz` SHALL be documented operationally without extending
the release-contract schema. Selected coordinates or npm-organization ownership alone MUST NOT
imply product-contract ownership.
Repository tooling MAY use explicit non-authoritative fixtures, but MUST NOT represent fixture
results or a merely selected incomplete contract as approved release evidence.

#### Scenario: A confirmed coordinate set is selected

- **WHEN** maintainers select confirmed names, independent exact versions, dependency
  ranges, release metadata, and an intended dist-tag
- **THEN** synchronized member manifests, peer requirements, and the producer lockfile
  match that external expected contract exactly

#### Scenario: The workspace root is inspected for release

- **WHEN** release readiness enumerates packable members
- **THEN** it excludes the private producer workspace root and evaluates each of the
  three member packages independently

#### Scenario: npm links the declared producer members

- **WHEN** the private producer lockfile represents each explicitly declared token, UI,
  and SDK member with `link: true` and a contained member-directory target
- **THEN** release validation accepts those expected workspace links while continuing to
  exclude the root from release

#### Scenario: A producer link is unexpected or escapes

- **WHEN** the producer lockfile links an undeclared package, resolves a declared member
  outside the producer workspace, or maps a package name to the wrong member directory
- **THEN** release validation fails and identifies the invalid link target

#### Scenario: A published manifest uses a local dependency

- **WHEN** a packed member manifest declares a `workspace:`, `file:`, `link:`, directory,
  checkout-source, or other local dependency reference
- **THEN** archive validation fails even if the producer workspace could resolve it

#### Scenario: An archive self-declares different metadata

- **WHEN** a candidate archive declares a name, version, dependency, export, license,
  repository field, or other required value that differs from the selected contract
- **THEN** validation fails even if the archive is internally self-consistent

#### Scenario: Required release ownership is incomplete

- **WHEN** a command attempts to create approved release evidence while a required owner or
  later publication-policy field remains unresolved
- **THEN** it fails actionably and does not label the archives release candidates

#### Scenario: npm organization ownership is recorded

- **WHEN** the selected contract records the confirmed `fred-oss` organization and bootstrap
  account owner role
- **THEN** tooling accepts the selected scope and bootstrap authority only when all selected
  package names belong to `@fred-oss/`, without inferring package API, SDK protocol, release, or
  enduring publishing ownership

#### Scenario: The complete maintainer contract is confirmed

- **WHEN** the selected contract records `marc.fawaz` for all four ownership roles and `direct`
  for the subsequent Trusted Publishing policy
- **THEN** contract validation reports no unresolved maintainer decisions while candidate
  execution and publication remain subject to their separate source, validation, manual-choice,
  and protected-environment gates

#### Scenario: A fixture contract is relabelled without maintainer decisions

- **WHEN** a fixture contract's state is changed while it retains fixture approval
  identities, development versions or tag, or non-authoritative provenance identities
- **THEN** validation rejects it before packing and it cannot produce approved candidate
  evidence

### Requirement: Candidate archives and evidence are immutable

Release-candidate validation SHALL operate on the actual packed bytes for all three
packages and SHALL preserve every existing design-token, UI, iframe SDK, isolated
consumer, browser, and production-host compatibility guarantee. A successful candidate
record MUST bind the source commit, exact Node and npm versions, selected package
coordinates, archive filenames, and SHA-512 integrity values to those bytes. It MUST also
bind the expected provenance source repository, source commit, authorized publishing
workflow identity, and artifact digest used by later registry verification. These
expected values MUST come from the approved release contract and candidate evidence, not
from a downloaded provenance statement.

Any archive that is rebuilt, renamed in a way that changes its recorded identity,
modified, or replaced after validation MUST receive fresh archive, consumer, browser,
host-compatibility, and integrity evidence. A later publication step MUST use the exact
validated bytes; it MUST NOT rebuild packages and treat the prior evidence as valid.

#### Scenario: Three candidate archives pass validation

- **WHEN** the selected source commit produces token, UI, and SDK tarballs whose metadata
  and contents satisfy the expected release contract and all existing archive gates
- **THEN** evidence records the exact toolchain, coordinates, filenames, and SHA-512
  integrity for each tarball together with its expected repository, commit, authorized
  publishing workflow identity, and attested artifact digest

#### Scenario: Candidate bytes change after validation

- **WHEN** any candidate tarball is rebuilt or its bytes no longer match the recorded
  SHA-512 integrity
- **THEN** prior candidate evidence is rejected and the complete validation sequence
  must run again

#### Scenario: Publication input differs from candidate evidence

- **WHEN** a future publication operation receives archive bytes other than the bytes
  identified by the reviewed evidence
- **THEN** it must stop before registry mutation rather than publishing a rebuild

### Requirement: Release validation uses an exact producer toolchain

Candidate generation and release-evidence production SHALL require exact, non-floating
Node and npm versions recorded in the release contract. The initial recommended pin is
Node `24.21.0` with npm `11.19.0`, which satisfies the currently documented minimums for
npm Trusted Publishing and staged publishing; changing either pin MUST be a reviewed
contract change with renewed validation.

FRED application tests that participate in compatibility validation MUST remain under
their separately controlled application toolchain. Release evidence MUST record exact
Node and npm versions for that application-test environment. Release orchestration MUST identify
which toolchain produced each item of evidence and MUST pass immutable candidate
archives between producer and application-test environments rather than resolving the
producer's installed dependencies from the application environment.

#### Scenario: Candidate production uses the pinned versions

- **WHEN** a release-candidate command starts with Node or npm different from the exact
  selected versions
- **THEN** it fails actionably before packing or recording candidate evidence

#### Scenario: Application compatibility runs on its own tooling

- **WHEN** CI executes FRED application regression or production-host compatibility
  checks against candidate archives
- **THEN** the application uses its independently pinned tooling and receives the exact
  candidate bytes without using the producer dependency tree

#### Scenario: The toolchain pin changes

- **WHEN** maintainers select a different exact Node or npm version
- **THEN** all three archives and their release evidence are regenerated and revalidated

### Requirement: Fixture transfer preserves exact producer archives across CI jobs

Before coordinates are maintainer-confirmed, CI MAY exercise the release-to-application toolchain
boundary with the development fixture contract. The release-toolchain producer SHALL create one
strictly fixture-labelled transfer containing exactly the three validated npm tarballs and
producer transfer metadata. The metadata MUST bind the checked-out source commit, fixture
contract digest, observed producer Node/npm versions, exact package roles, coordinates,
filenames, byte lengths, SHA-512 values, and repository/workflow/run/attempt identity. It MUST
state that downstream consumer, browser, and host gates have not run, and MUST NOT be classified
as approved candidate or public-registry evidence. The retained artifact MUST exclude credentials,
installed dependencies, consumer caches, and checkout content and MUST use an explicit retention
period and source/run-specific fixture name.

The application-toolchain receiver MUST obtain that exact artifact from its producer dependency
in the same workflow execution, MUST independently select the expected checkout commit and
fixture contract, and MUST validate the metadata plus exact archive file set before extraction,
installation, or execution. It MUST reject missing, additional, non-regular, substituted,
truncated, or modified files; wrong commits, contract digests, package identities, versions, or
run associations; and missing, malformed, or inconsistent integrity metadata. It MUST pass only
verified explicit archive paths and expected integrities to the existing isolated consumers,
browser harness, and production-host SDK integration. It MUST NOT rebuild or repack the received
archives, use mutable latest-run selection or `target/` archive defaults, fall back to package
sources or workspace dependencies, or transfer installed dependency trees between jobs.

Final fixture validation evidence MUST be written only after all required receiver gates succeed.
It MUST retain the `fixture-candidate-evidence` classification, bind the original transfer
metadata digest and artifact identity to the exact archive records, record the receiver's actually
observed application Node/npm versions separately from producer versions, and include the
consumer, browser, and host results. An incomplete receiver run MUST NOT leave successful final
evidence. Fixture transfer or validation evidence MUST NOT satisfy approved-candidate retention,
exact-toolchain candidate execution, or genuine registry-verification requirements.

#### Scenario: A valid fixture set crosses the toolchain boundary

- **WHEN** the release-toolchain job uploads its source/run-specific three-archive fixture and the
  dependent application-toolchain job receives it in the same workflow attempt
- **THEN** the receiver verifies the metadata and exact bytes before reusing those paths without
  invoking any package build or pack operation

#### Scenario: Transfer contents are incomplete or substituted

- **WHEN** an archive or metadata file is missing or additional, non-regular, truncated, modified,
  or inconsistent with its recorded length or SHA-512
- **THEN** transfer validation fails before installation or package execution and does not search
  local generated archives for a replacement

#### Scenario: Transfer identity differs from receiver expectations

- **WHEN** source commit, contract digest, package coordinate, repository, workflow, run, or
  attempt differs from the receiver's independently selected expectation
- **THEN** transfer validation rejects the complete set before any downstream gate runs

#### Scenario: A downstream fixture gate fails

- **WHEN** any isolated consumer, browser smoke, or production-host integration gate fails after
  transfer verification
- **THEN** no successful final fixture-candidate evidence record is written

#### Scenario: A downstream gate changes a transferred archive

- **WHEN** a downstream gate mutates an archive after initial transfer verification but otherwise
  reports success
- **THEN** the receiver's post-gate byte-length and SHA-512 verification fails and no final
  fixture-candidate evidence record re-baselines the changed bytes

#### Scenario: A fixture record is presented as approved evidence

- **WHEN** intermediate transfer metadata or final fixture validation evidence is supplied to an
  approved candidate, publication, or public-registry verification path
- **THEN** the operation rejects the fixture classification regardless of otherwise matching
  archive hashes

### Requirement: Candidate versions work in isolated consumers

The existing neutral token, React UI, and framework-independent iframe SDK consumers
SHALL accept the exact selected candidate coordinates and install the actual candidate
archives in fresh locations outside the FRED checkout. Provisioning MAY populate only
the lockfile-pinned caches and browser prerequisites declared for those selected
coordinates. Offline validation MUST retain source isolation, production builds,
browser checks, and SDK production-host compatibility without network access, directory
dependencies, workspace links, local source fallback, or resolution from FRED's installed
dependency tree.

Disposable offline consumer manifests and lockfiles MAY contain npm-generated `file:`
references to the exact staged candidate `.tgz` files. Each permitted reference MUST
map by package identity to an approved candidate evidence record, identify a regular
non-symlink tarball file whose real path remains inside the disposable consumer, and match
the recorded archive filename and bytes. Every permitted declaration MUST use exactly
`file:<approved-record-filename>`; alternative spellings MUST be rejected rather than
normalized. A dependency declaration legitimately has no integrity field, but every direct or
nested local package-resolution entry MUST contain a valid SRI SHA-512 integrity value and it
MUST exactly match the approved record. Validation MUST inspect all
applicable root and nested manifest/lock dependency fields and local lock resolutions before
dependency installation; a matching archive basename alone MUST NOT authorize a reference.
Noncanonical tilde, whitespace or control-character, dot-segment, percent-encoded, query,
fragment, backslash, absolute, or escaping forms MUST be rejected so validation and npm cannot
resolve different targets. Local Git checkout references such as `git+file:` MUST be rejected
case-insensitively, including leading whitespace that npm may normalize.
No directory target, unexpected or additional local file, checkout path, unmatched nested
dependency, symlinked package, or reused FRED dependency tree is permitted.
Production-host integration MUST run the host with dependencies installed from the FRED
application's own lockfile while loading the SDK under test only from its verified archive
or exact registry installation.

#### Scenario: Candidate archives replace development versions

- **WHEN** isolated consumers are configured with the selected token, UI, and SDK
  candidate coordinates and matching lockfiles
- **THEN** offline installation, type checking, production builds, browser smoke, and
  host compatibility pass with the actual candidate tarballs

#### Scenario: npm records a verified candidate tarball

- **WHEN** disposable offline installation records a `file:` dependency or lockfile
  resolution for a staged candidate `.tgz` whose bytes match the recorded SHA-512
- **THEN** validation accepts that archive reference and installs the packed package

#### Scenario: A local reference targets a directory or different file

- **WHEN** a disposable consumer reference resolves to a directory, workspace member,
  symlink, checkout path, or local file other than the integrity-verified staged tarball
- **THEN** isolated-consumer validation fails before building

#### Scenario: An additional lock entry reuses an approved filename

- **WHEN** a root or nested lock entry names an unapproved package, escapes the consumer, or
  resolves different bytes under the same basename as an approved candidate archive
- **THEN** isolated-consumer validation fails before `npm ci` despite the filename match

#### Scenario: A nested local dependency lacks matching evidence

- **WHEN** any dependency-reference field or local lock resolution identifies a package,
  archive real path, version, or integrity value that does not match its approved evidence
- **THEN** isolated-consumer validation rejects the complete graph before dependencies are used

#### Scenario: A file reference encodes a different path

- **WHEN** a local tarball reference uses encoded traversal or separators, a query, a fragment,
  or a backslash that npm could interpret differently from a literal filesystem check
- **THEN** isolated-consumer validation rejects the ambiguous reference before dependency use

#### Scenario: npm would normalize a noncanonical local reference

- **WHEN** a local declaration or resolution uses a tilde, an actual tab, a dot segment, or any
  spelling other than `file:<approved-record-filename>`
- **THEN** isolated-consumer validation rejects it before dependency installation even if a
  literal filesystem lookup would find bytes matching the candidate

#### Scenario: A local Git checkout is declared

- **WHEN** an offline or published-package dependency uses `git+file:` with any casing or
  leading whitespace
- **THEN** validation rejects the local checkout reference before dependency installation or
  archive acceptance

#### Scenario: A local package resolution omits integrity

- **WHEN** a direct or nested local package-resolution entry has missing, null, empty, malformed,
  or mismatched integrity
- **THEN** isolated-consumer validation rejects the graph before dependency installation while
  continuing to permit declarations without their own integrity field

#### Scenario: A consumer resolves a development or workspace package

- **WHEN** a candidate consumer graph contains `0.0.0-development`, a workspace link, a
  directory dependency, an unverified local file dependency, or a package resolved from
  the FRED checkout or its installed dependency tree
- **THEN** release-candidate validation fails

#### Scenario: Production host compatibility uses the packed SDK

- **WHEN** the production-host integration gate exercises an SDK candidate
- **THEN** the host test runner and application modules resolve from the FRED application's
  own lockfile installation while the SDK entry resolves from the integrity-verified
  candidate archive, not the producer workspace

#### Scenario: Candidate provisioning is incomplete

- **WHEN** an exact dependency or browser prerequisite is absent from the prepared cache
- **THEN** offline validation fails actionably without fetching or installing it

### Requirement: Registry verification is exact and cannot fall back locally

The repository SHALL provide a registry-verification command that accepts the exact
expected coordinate and previously recorded archive SHA-512 integrity for each FRED
package. Against a real public registry, it MUST resolve those exact versions, verify
registry-reported and downloaded-byte integrity, cryptographically verify provenance for
each package, and exercise fresh clean consumers installed from the registry.

Before installing each resolved package, the verifier MUST compare its exact identity, version,
registry, and downloaded SHA-512 with the approved contract and candidate evidence. It MUST
generate and validate the disposable registry lock graph against those same expectations,
including every FRED package resolution present in the graph. Only an accepted graph may be
installed with lifecycle scripts disabled. Before running `npm audit signatures`, the verifier
MUST prove through npm's actual installed-tree behavior and the installed package's filesystem
identity that the exact package is a non-linked installed dependency contained in the fresh
disposable root. A package-lock without the corresponding installation MUST NOT satisfy this
gate. Installation or audit MUST NOT use a local tarball, workspace, checkout, application
`node_modules`, or other fallback.

Cryptographic signature validity alone MUST NOT establish a matching release. Cryptographic
verification MUST require the signing certificate identity to equal the explicitly authorized
GitHub workflow URI and its issuer to equal the explicitly expected GitHub Actions OIDC issuer.
For every package, verification MUST then independently compare the attested artifact digest,
source repository,
source commit, and publishing workflow identity with the explicit expected values bound
to the approved release contract and candidate evidence. It MUST NOT accept values merely
because they appear in a validly signed downloaded attestation. The expected bootstrap
identity and the later authorized Trusted Publishing workflow identity MUST remain
distinct and explicit; an unconfirmed identity MUST fail closed as a maintainer decision.
The source commit MUST be selected from exactly one resolved dependency whose normalized URI
identifies the explicitly expected source repository. An unrelated dependency's commit MUST NOT
satisfy that comparison, and a missing or ambiguous matching dependency MUST fail closed.

The command MUST reject tags, ranges, unexpected registries, missing provenance,
integrity mismatches, local tarballs, workspace packages, source-checkout resolution,
and silent fallback. Its local automated tests MUST use controlled registry fixtures or
equivalent deterministic responses and MUST label their result as tooling validation,
not as proof that packages were genuinely published.

The command MUST discover the attestation document from npm's raw
`dist.attestations.url` version-metadata field, MUST validate that it is an allowed npm
attestation endpoint for the exact expected coordinate, and MUST re-root its pathname onto
the explicitly approved registry before fetching. It MUST reject a missing, malformed,
credential-bearing, non-HTTP(S), fragment-bearing, endpoint-mismatched, or
coordinate-mismatched URL. The sibling provenance predicate metadata MUST NOT be treated as
the endpoint location.

Browser verification MUST use an explicit pre-provisioned Playwright browser directory shared
by the provisioning and verification steps. Before registry verification begins, the command
MUST confirm that Playwright resolves Chromium from that directory and that the executable
exists. Missing, default-cache, or differently resolved Chromium MUST fail actionably; registry
verification MUST NOT install or download a browser.

After exact-version metadata establishes the expected name, version, and candidate SHA-512, the
verifier MAY perform bounded read-only package-wide metadata readiness checks required by npm
transport. It MUST retry only an actual package-wide HTTP 404 and MUST fail immediately on
authentication or authorization errors, redirects, malformed metadata, or identity/integrity
mismatches. It MUST NOT interpret readiness as release identity, repeat publication, or use a
local archive when npm transport remains unavailable.

#### Scenario: Published candidates match recorded evidence

- **WHEN** the command is given the three exact published coordinates and their recorded
  integrity values and the public registry serves matching packages with provenance
- **THEN** clean registry-only token, UI, and SDK consumers pass their applicable build,
  browser, and compatibility checks

#### Scenario: npm metadata provides the attestation endpoint

- **WHEN** exact-version metadata supplies a valid `dist.attestations.url` for the selected
  coordinate
- **THEN** the verifier fetches that endpoint only through the approved registry and performs
  the required cryptographic and expected-release identity checks

#### Scenario: An approved registry graph is installed before signature audit

- **WHEN** exact registry metadata and archive bytes match candidate evidence and the generated
  lock graph contains only approved registry resolutions
- **THEN** the verifier validates that graph, installs it with lifecycle scripts disabled,
  proves the exact package exists in npm's installed tree, and only then runs npm signature audit

#### Scenario: A lockfile exists without an installed dependency tree

- **WHEN** registry resolution produced a package-lock but the exact dependency has not been
  installed in the disposable root
- **THEN** verification fails before npm signature audit rather than treating the lockfile as an
  installed tree

#### Scenario: The disposable registry graph has an unapproved resolution

- **WHEN** the generated graph contains a FRED package with a mismatched version or integrity,
  an unexpected registry, a link, or a local/workspace/checkout fallback
- **THEN** verification fails before dependency installation and provenance acceptance

#### Scenario: The provisioned browser is reused during registry verification

- **WHEN** the post-publication job provisions Chromium in its explicit Playwright directory and
  invokes registry verification with the same directory
- **THEN** the verifier confirms the selected executable is present inside that directory and
  browser smoke performs no browser installation or download

#### Scenario: Registry Chromium prerequisites are absent or inconsistent

- **WHEN** the explicit Playwright directory is missing, Chromium is absent, or Playwright
  resolves its executable from another directory
- **THEN** registry verification fails with an actionable provisioning error before registry
  resolution rather than bootstrapping a browser

#### Scenario: The attestation endpoint metadata is invalid

- **WHEN** `dist.attestations.url` is absent, malformed, disallowed, or names a different
  package coordinate or endpoint
- **THEN** registry verification fails before accepting or fetching provenance

#### Scenario: Valid provenance names an unexpected repository

- **WHEN** a provenance statement is cryptographically valid but its source repository
  differs from the repository expected by the approved contract and candidate evidence
- **THEN** registry verification fails the release-identity comparison

#### Scenario: Valid provenance names an unexpected commit

- **WHEN** a provenance statement is cryptographically valid but its source commit differs
  from the candidate source commit recorded as expected
- **THEN** registry verification fails the release-identity comparison

#### Scenario: Valid provenance names an unexpected workflow

- **WHEN** a provenance statement is cryptographically valid but its publishing workflow
  identity differs from the explicitly authorized Trusted Publishing identity
- **THEN** registry verification fails the release-identity comparison

#### Scenario: A valid Sigstore bundle has an unauthorized signer identity

- **WHEN** a provenance bundle is cryptographically valid but its signing certificate URI
  or issuer differs from the expected Trusted Publishing workflow certificate policy
- **THEN** registry verification fails before accepting statement identity claims

#### Scenario: Valid provenance names an unexpected artifact digest

- **WHEN** a provenance statement is cryptographically valid but its attested artifact
  digest differs from the expected digest of the candidate tarball
- **THEN** registry verification fails even if registry metadata reports another
  internally consistent integrity value

#### Scenario: Registry content does not match the candidate

- **WHEN** registry metadata, downloaded bytes, or provenance is missing or differs from
  the expected coordinate and integrity
- **THEN** verification fails and does not substitute a local archive or source tree

#### Scenario: Package-wide metadata becomes visible after the exact version

- **WHEN** exact-version metadata already matches approved identity and SHA-512 while npm's
  package-wide metadata initially returns 404 and then returns the same exact version
- **THEN** the verifier performs bounded read-only readiness retries and continues once without
  changing the release identity or invoking publication

#### Scenario: Package-wide readiness cannot establish matching metadata

- **WHEN** package-wide 404 retries are exhausted or a read is unauthorized, redirected,
  malformed, or inconsistent with the exact expected version and integrity
- **THEN** verification fails before npm transport, consumers, or evidence completion and does
  not fall back to local bytes

#### Scenario: A registry consumer attempts local fallback

- **WHEN** a registry-installed consumer resolves a FRED package from a tag, range, local
  tarball, directory, workspace, checkout source, or reused FRED dependency tree instead
  of the expected exact registry version
- **THEN** verification fails rather than accepting the consumer result

#### Scenario: Only verifier tooling was tested locally

- **WHEN** the verifier passes against controlled local fixtures without genuinely
  published package coordinates
- **THEN** evidence reports only that verifier behavior passed and does not report a
  successful public-registry release verification

### Requirement: Bootstrap, publication, and adoption remain separate gates

Release documentation SHALL distinguish repository readiness, initial npm package
creation, later Trusted Publishing configuration, optional staged-publishing policy,
actual publication, registry verification, FRED adoption, and external adoption.
Initial creation MUST require confirmed scope ownership and an account or organization
permission model capable of creating each package; it MUST NOT assume that a
package-scoped credential can create a nonexistent package. Staged publishing MUST be
documented as an available policy with prerequisites and MUST NOT be used for brand-new package
creation; the selected policy for subsequent FRED frontend package releases SHALL be direct
Trusted Publishing with GitHub environment approval. The bootstrap actor or credential identity
and the later Trusted Publishing workflow identity MUST be recorded separately. Neither identity
may be inferred from the other, and an unconfirmed identity remains a maintainer gate.

Dependencies SHALL be released before consumers: a compatible design-token version
before its UI consumer, while the independent SDK may be sequenced separately. FRED
adoption SHALL occur only after the required prereleases pass genuine registry
verification. If later protocol-ownership transfer changes SDK bytes, the corresponding
SDK version MUST be built, validated, and published before FRED adopts it. RAGS adoption
remains separately tracked and MUST use the same generic contract as any external
application.

Published versions MUST be treated as immutable. Recovery SHALL select a previously
validated version or publish a newly versioned correction; it MUST NOT overwrite a
published version. Adoption rollback SHALL restore a prior lockfile/dependency set or
redeploy a prior application image.

The repository SHALL provide a dedicated `workflow_dispatch`-only first-release workflow that
rejects refs other than `swift`, defaults to candidate preparation without publication, and
requires an explicit manual publication choice. Candidate production and application-toolchain
validation MUST be separate jobs that transfer one commit/run-specific immutable archive set.
The application job MUST verify the transfer before and after its offline consumer, browser, and
production-host gates and add approved evidence only for a complete `maintainer-confirmed`
contract. The workflow MUST NOT rebuild archives during or after this transfer.

Initial publication MUST use a protected GitHub environment named `npm-publish`. The environment
secret `NPM_BOOTSTRAP_TOKEN` MUST be referenced only by an explicitly selected initial or
partial-recovery publishing step and
MUST NOT be available to checkout, installation, build, test, transfer, or registry-verification
steps. The publishing job MUST grant `id-token: write`, reverify the exact archive bytes and
evidence, require the expected repository, commit, ref, workflow identity, and authenticated
bootstrap account, and preflight that all three exact versions are absent before the first
registry mutation. It MUST publish design tokens before UI, use public access and `next`, request
GitHub Actions provenance, and verify registry integrity after each successful package publish.
The SDK MAY follow independently within the same sequence.

Post-publication reconciliation MUST query the configured registry's exact-version HTTP endpoint
directly, without requiring package-wide metadata, and require the selected name, version, and
candidate SHA-512. The request MUST be bounded, MUST NOT follow a redirect away from the approved
request, and MUST use bounded retries only when that exact endpoint returns an actual HTTP 404.
It MUST NOT retry a publication command. Authentication or authorization failures, other HTTP
failures, redirects, timeouts, malformed metadata, identity or integrity mismatches, and exhausted
visibility retries MUST stop before the next package. Bootstrap preflight, reconciliation,
recovery state checks, and registry-verifier metadata resolution MUST share this behavior.

A preflight existing version or a failure after partial publication MUST stop without rebuilding,
overwriting, or silently accepting different bytes. Logs and evidence SHALL identify which exact
packages succeeded so maintainers can choose an explicit recovery. Ordinary bootstrap MUST
continue to reject every pre-existing selected coordinate. A partial-bootstrap recovery MAY
reuse unchanged original candidate bytes only through a separate manual operation that pins and
verifies the original artifact identity and digest, verifies every already-published coordinate's
exact bytes and cryptographic provenance, requires every remaining coordinate to be absent, and
publishes only those absent archives behind the same protected environment. If those conditions
fail, recovery MUST use a newly versioned candidate. If a publish command
fails after the registry may have accepted it, the workflow MUST query that exact coordinate and
compare integrity before reporting the outcome. Matching bytes MAY be reported as confirmed;
otherwise the outcome MUST remain explicitly indeterminate and MUST NOT be described as no
registry mutation. A genuine registry
verification job MUST run only after the explicitly selected publication path and MUST use exact
registry coordinates, recorded integrity, and provenance without receiving the bootstrap secret.
Its clean-consumer, browser, and production-host checks MUST execute under the separately selected
application toolchain rather than the release-production Node/npm installation.
Local workflow and publication-helper tests MUST remain controlled tooling evidence and MUST NOT
claim GitHub environment approval, emitted provenance, package creation, or public-registry
success.

Recovery preparation and protected publication MUST each verify the pinned original ZIP, reject
missing, additional, traversal, linked, special, or otherwise unsafe candidate entries, and
extract its exact candidate evidence, transfer metadata, and three archives into a fresh isolated
directory. They MUST validate those files as one original candidate set. The protected boundary
MUST reject any separately transferred candidate copy that differs from the ZIP and MUST publish
only archive paths derived from its fresh verified extraction. It MUST clean that extraction and
MUST NOT regenerate or re-baseline the original evidence.

Reusable recovery plan, identity, provenance-expectation, and evidence validation MUST be
independent of either executable CLI module. Recovery preparation MUST be able to dynamically load
the real registry verifier for existing-package provenance without a circular module-evaluation
wait, while the registry-verifier CLI MUST continue to load and enforce recovery evidence. CLI
errors MUST propagate as nonzero exits. Controlled acceptance tests MUST execute the actual entry
points in fresh processes with bounded timeouts and MUST NOT replace or bypass the existing-package
verification path.

After the three versions exist, the workflow SHALL provide a separate `verify-existing` choice
that schedules only source authorization, pinned publication-evidence retrieval, dependency and
browser provisioning, and public-registry verification. It MUST NOT schedule candidate creation,
candidate compatibility transfer, bootstrap publication, or recovery publication. It MUST use
only read access needed for artifact retrieval and MUST NOT use the `npm-publish` environment,
`NPM_BOOTSTRAP_TOKEN`, publishing credentials, or `id-token: write`.

Verification continuation MUST pin and validate the retained recovery artifact's ID, name,
source commit, run/attempt, API digest, and downloaded ZIP SHA-256. It MUST validate the outer ZIP
and its exact regular-file set, the nested original candidate ZIP and metadata, every unchanged
candidate/recovery evidence record, and every archive copy before registry access. Historical
publication expectations MUST remain bound to each package's actual publication commit and
workflow; the current verification commit, run, and attempt MUST be recorded separately from
GitHub's actual execution without overwriting, relabelling, or spoofing historical evidence.

The same unexpired retained artifact MAY be verified by more than one later workflow execution.
Final public-registry evidence MUST be written and retained only after all three exact registry
archives and lock graphs, npm signatures, Sigstore bundles, expected provenance identities,
clean registry consumers, browser smoke, and production-host compatibility succeed.

#### Scenario: Maintainers bootstrap a new public package

- **WHEN** one of the selected package names does not yet exist in the approved npm scope
- **THEN** maintainers verify organization ownership and package-creation authority and
  record the authorized bootstrap identity before using the approved bootstrap process
  and separately configuring the later Trusted Publishing workflow identity

#### Scenario: Preparation is dispatched without publication

- **WHEN** a maintainer manually dispatches the first-release workflow on `swift` with its default
  input
- **THEN** it prepares and validates the immutable candidate under both toolchains without
  receiving a registry credential or executing a publish command

#### Scenario: Bootstrap publication is explicitly selected

- **WHEN** a maintainer selects bootstrap publication and the protected environment approves a
  complete candidate from the same committed workflow run
- **THEN** only the publishing step receives `NPM_BOOTSTRAP_TOKEN`, reverifies the evidence and
  bytes, requests provenance, and publishes in dependency-safe order

#### Scenario: A first-release coordinate already exists

- **WHEN** preflight finds any selected exact version already present on the public registry
- **THEN** publication stops before its first mutation and reports a partial or conflicting
  release rather than overwriting or accepting unknown bytes

#### Scenario: Publication fails after one package succeeds

- **WHEN** a package publish or integrity check fails after an earlier package was created
- **THEN** the workflow stops and retains immutable evidence and logs; a separately reviewed
  partial recovery may use the same unchanged bytes only when the published subset and missing
  subset satisfy the recovery contract, otherwise a newly versioned candidate is required

#### Scenario: Exact-version visibility is delayed after publication

- **WHEN** an exact-version lookup returns 404 immediately after one publish command and a bounded
  later read returns matching name, version, and candidate SHA-512 metadata
- **THEN** the workflow records that package once and proceeds without executing another publish
  command for it

#### Scenario: Package-wide metadata is unavailable for a visible exact version

- **WHEN** package-wide registry metadata returns 404 but the exact-version HTTP endpoint returns
  matching name, version, and candidate SHA-512 metadata
- **THEN** bootstrap and recovery use the exact-version result without consulting package-wide
  metadata or repeating a publication command

#### Scenario: Post-publication reconciliation cannot establish exact identity

- **WHEN** exact-version visibility retries are exhausted, the registry read is unauthorized, or
  metadata is malformed or differs in package name, version, or candidate SHA-512
- **THEN** the workflow stops before the next package and does not repeat the publication command

#### Scenario: Maintainers explicitly recover the recorded partial bootstrap

- **WHEN** a maintainer selects partial recovery for the pinned original artifact, preparation
  verifies its ID/name/ZIP digest and unchanged candidate evidence, cryptographically verifies
  the existing design-token version, and confirms UI and SDK are absent
- **THEN** protected-environment recovery may publish only the original UI and SDK archives in
  order, with no design-token publication command

#### Scenario: A transferred recovery copy differs from the pinned ZIP

- **WHEN** the pinned original ZIP is unchanged but a transferred archive, candidate evidence, or
  transfer metadata copy is replaced and internally re-baselined
- **THEN** both preparation and protected publication reject the mismatch before any publication
  callback, and publication never uses the replacement archive

#### Scenario: The pinned recovery ZIP has an unsafe or unexpected entry

- **WHEN** the recovery ZIP contains traversal, a link or special file, an omitted expected file,
  or an additional candidate file
- **THEN** recovery rejects it before extracting or resolving any registry state

#### Scenario: Recovery preparation loads the real verifier in a fresh process

- **WHEN** the recovery preparation CLI verifies the published design-token package and
  dynamically loads the registry verifier from a fresh Node process
- **THEN** module evaluation completes, cryptographic provenance is enforced, recovery evidence is
  written only on success, and the process does not exit with an unsettled top-level await

#### Scenario: Recovery-aware registry verification loads the shared evidence contract

- **WHEN** the public-registry verifier CLI receives a recovery plan and evidence
- **THEN** it imports the independent validation contract, rejects invalid recovery evidence, and
  continues past valid evidence without importing the executable recovery entry module

#### Scenario: Maintainers continue verification without publication

- **WHEN** all three coordinates already exist and a maintainer dispatches `verify-existing` on
  `swift` against the pinned retained recovery artifact
- **THEN** only authorization, artifact retrieval/verification, provisioning, and registry
  verification run, with no protected environment, credential, candidate build, or publication

#### Scenario: Historical publication and current verification differ

- **WHEN** a later workflow verifies packages published by the original and recovery commits
- **THEN** provenance is checked against each historical publication commit while final evidence
  separately records the verifier's actual current commit, run ID, and attempt

#### Scenario: A retained verification artifact or copy differs

- **WHEN** the recovery artifact metadata or ZIP, nested original ZIP, evidence, or archive copy
  differs from its reviewed identity and digest
- **THEN** verification stops before registry consumption and does not rebuild, re-baseline, or
  substitute the candidate

#### Scenario: The same retained publication is verified again

- **WHEN** another `verify-existing` execution receives the same unexpired pinned artifact and all
  immutable checks pass
- **THEN** it may repeat the complete read-only verification and records its own execution
  identity without requiring any package to be absent

#### Scenario: A continuation gate fails before completion

- **WHEN** any archive, registry, signature, provenance, consumer, browser, or host gate fails
- **THEN** no completed public-registry verification evidence is retained and no publication path
  is scheduled

#### Scenario: A recovery subprocess encounters a validation or publication failure

- **WHEN** the original artifact, transferred copies, existing-package provenance, or publication
  operation fails in a fresh recovery CLI process
- **THEN** it returns a nonzero exit, performs no forbidden or subsequent publication, and cannot
  hang beyond the bounded test deadline

#### Scenario: Recovery and original provenance have different source commits

- **WHEN** the retained candidate came from the original commit but missing packages are
  published by a later recovery workflow execution
- **THEN** evidence preserves the original artifact commit/run unchanged, requires the existing
  design token to attest the original source commit, and requires UI and SDK to attest the actual
  recovery `GITHUB_SHA`, while retaining the approved repository, workflow, issuer, and archive
  digests

#### Scenario: Partial recovery prerequisites drift

- **WHEN** the original artifact expires or changes, an existing package differs in bytes or
  provenance, a supposedly missing coordinate appears, or recovery execution identity differs
- **THEN** recovery stops before publication and requires an explicit newly versioned path rather
  than relabeling evidence, spoofing GitHub identity, or weakening provenance checks

#### Scenario: A publish command fails after an ambiguous registry mutation

- **WHEN** a publish command fails after the registry may have accepted the candidate bytes
- **THEN** the workflow reconciles the exact coordinate and integrity, reports matching bytes as
  confirmed or the result as indeterminate, and stops without rebuilding or continuing

#### Scenario: A local publication test passes

- **WHEN** controlled tests exercise the bootstrap helper and workflow contract without an actual
  GitHub environment and public npm packages
- **THEN** they report tooling validation only and do not claim publication, provenance, or
  registry-verification success

#### Scenario: Maintainers choose staged publishing

- **WHEN** staged publishing is selected as release policy
- **THEN** it is used only after the package exists and the required npm, Node, access,
  and two-factor approval prerequisites are satisfied

#### Scenario: FRED adoption is proposed

- **WHEN** maintainers prepare a later change to consume registry packages in FRED
- **THEN** the required prereleases already have matching integrity, provenance, and
  clean-consumer registry evidence, and any changed SDK artifact is released first

#### Scenario: A released candidate must be rolled back

- **WHEN** a defect is found after publication or adoption
- **THEN** maintainers deprecate or supersede the affected version and restore a prior
  validated dependency set or image without replacing published bytes
