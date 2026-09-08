## Purpose

Defines how FRED produces and verifies self-contained frontend package archives that
external applications can install without access to the FRED source checkout.

## ADDED Requirements

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
