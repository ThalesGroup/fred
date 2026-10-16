## Purpose

Allow developers to prepare Fred images and deploy the product chart to a local Kubernetes installation reproducibly, without changing existing data or exposing secrets.

## ADDED Requirements

### Requirement: Installation configuration remains inspectable and separate from product builds
The local deployment SHALL use the product chart and the instance's k3d values (the factory's `k3d-apps/<app>/values.yaml` for Fred and the evaluation application, a product's `deploy/k3d/values.yaml` otherwise), retain the configured release and namespace identities, and expose standard Helmfile validation and deployment commands. Chart defaults, the k3d values, generated image overrides and any factory-supplied extra values SHALL apply in that order. Missing paths or invalid values MUST fail clearly, and paths containing spaces MUST work independently of the caller's directory.

#### Scenario: Existing installation is redeployed
- **WHEN** the developer deploys Fred with default local settings
- **THEN** the existing `fred-app` release in namespace `fred` is upgraded using the checkout's chart and its k3d values
- **AND** the `fred-stack` release is not redeployed or uninstalled

#### Scenario: Checkout path includes spaces
- **WHEN** the checkout path contains spaces and the command is invoked from another directory
- **THEN** the same files and value precedence are used without shell splitting

### Requirement: Published releases deploy without a checkout
The factory SHALL define Fred and the evaluation application in `k3d-apps/<app>/` (helmfile, k3d values, identities, hooks) and deploy each one's published OCI chart and images at a pinned default version, with no checkout and no build. `RELEASE` SHALL select another published version; a value that is not a release version MUST fail before any cluster mutation. With `DIR`, the same definition SHALL use the checkout's chart and the images its `deploy/k3d/build` produces.

#### Scenario: Deploying the pinned releases
- **WHEN** the developer runs `make k3d-app APP=fred` then `make k3d-app APP=fred-evaluator` with no checkout
- **THEN** the `fred-app` and `fred-evaluator` releases run the published charts and `ghcr.io` images at the factory's pinned versions
- **AND** the evaluation application is registered with Fred

#### Scenario: Deploying another release
- **WHEN** the developer adds `RELEASE=3.6.0`
- **THEN** chart `fred` 3.6.0 and the `ghcr.io/thalesgroup/fred-agent/*:v3.6.0` images are deployed

#### Scenario: Version is not a release
- **WHEN** `RELEASE` is `latest` or another non-version string
- **THEN** the command fails and nothing is deployed

#### Scenario: Development from a checkout
- **WHEN** the developer runs `make k3d-app APP=fred DIR=../fred`
- **THEN** the checkout's chart is deployed with images built by its `deploy/k3d/build` and the factory's values

#### Scenario: Product-owned application
- **WHEN** the developer runs `make k3d-app DIR=<checkout>` on a checkout with its own `deploy/k3d/helmfile.yaml.gotmpl`
- **THEN** the deployment behaves as before

### Requirement: Image preparation preserves service and worker consistency
The local build SHALL prepare Fred's four application images through existing product build tools, tag them according to their image content, and use each backend image for its corresponding worker. Failed builds MUST stop deployment.

#### Scenario: Backend image changes
- **WHEN** a knowledge-flow or control-plane backend image has different content
- **THEN** both that backend and its worker receive the same new image reference
- **AND** an unchanged image retains its reference

### Requirement: Validation is non-mutating and precedes deployment
Validation SHALL lint and render the effective chart values without building, importing images, patching secrets, recovering releases or mutating Kubernetes. Deployment SHALL validate configuration before builds and validate final image overrides before cluster mutations. All cluster operations MUST explicitly target the requested context without switching the global current context.

#### Scenario: Rendering fails
- **WHEN** chart rendering rejects an installation value or final image override
- **THEN** no subsequent image import, secret patch or Helm recovery/deployment occurs

#### Scenario: Validation is invoked alone
- **WHEN** the developer invokes the documented validation command
- **THEN** no image build or cluster mutation occurs
- **AND** the result states whether prepared image overrides were included

### Requirement: Local bootstrap and operational behavior are preserved safely
Deployment SHALL preserve model-key synchronization and restart its existing consumers when required, provision Fred dashboards, wait for rollout readiness and explain initial bootstrap/access. Secret contents MUST remain outside tracked files, command arguments and deployment logs. Existing PVC recovery protections MUST remain in force.

#### Scenario: Model key changes on an existing deployment
- **WHEN** a supplied model key differs from the stored key
- **THEN** the key is updated without being printed and its consumers reload it before success is reported

#### Scenario: A failed release owns persistent claims
- **WHEN** recovery finds no previously deployed revision and the release owns PVCs
- **THEN** it refuses automatic uninstall and reports the condition without deleting data

#### Scenario: Initial bootstrap is required
- **WHEN** Fred reports that initial platform bootstrap is still required
- **THEN** the developer receives login and local token-retrieval instructions without the token in deployment logs
