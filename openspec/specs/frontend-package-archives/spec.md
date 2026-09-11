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
workspace; a consumed canonical component, type, or stylesheet; the FRED frontend
React manifest or lockfile baseline; a packaged Geist or Material Symbols asset; an
applicable license or notice input; or relevant validation orchestration changes. It MAY
skip that job for application changes that do not affect any package-validation input.

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
  notice input applicable to either generated archive
- **THEN** CI selects the frontend-package validation job

#### Scenario: Validation orchestration changes

- **WHEN** a pull request changes a root command, workflow, setup action, build
  configuration, fixture lockfile, or validation script that controls the
  frontend-package gates
- **THEN** CI selects the frontend-package validation job

#### Scenario: An unrelated application file changes

- **WHEN** a pull request changes only application files that are not consumed by or
  responsible for frontend-package validation
- **THEN** CI may skip the frontend-package validation job

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
