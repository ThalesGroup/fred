<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/fred-banner-dark.svg">
    <img alt="Fred" src="docs/assets/fred-banner.svg" width="300">
  </picture>
</p>

# Fred

Fred is an open-source platform for working with AI agents and documents under
shared identity, permissions and organization governance.

## Start here

- [Architecture and user journeys](docs/architecture/README.md): the maintained
  explanation of current Fred behavior.
- [First local deployment](deploy/k3d/README.md#first-start-on-k3d): prerequisites,
  startup and provisioning commands.
- [Local development](scripts/README-local-delegation.md): run components against
  the local infrastructure.
- [Coding conventions](docs/CONVENTIONS.md) and [agent instructions](AGENTS.md).

## Components

| Component | Responsibility |
| --- | --- |
| [Control Plane](apps/control-plane/README.md) | Organizations, spaces, permissions, document metadata and agent administration; PostgreSQL persistence and Rust permission evaluation. |
| [Knowledge Flow](apps/knowledge-flow-backend/README.md) | Document processing and knowledge retrieval. |
| [Agent Pod](apps/fred-agents/README.md) | Runs agents with the Python runtime and capability libraries. |
| [Frontend](apps/frontend/README.md) | User interface for the platform. |
| [SDK](libs/fred-sdk/README.md), [runtime](libs/fred-runtime/README.md), [core](libs/fred-core/README.md) | Agent contracts, execution and shared infrastructure. |
| [Frontend libraries](libs/frontend/README.md) | Shared UI packages and their release tooling. |

The architecture dossier describes integrated user journeys. A library or API
being present in the repository does not by itself establish an available journey.

## Architecture and implementation

Code, database migrations and executable checks establish implementation facts.
The [arc42 dossier](docs/architecture/README.md) explains responsibilities,
boundaries, guarantees and their reasons. Its technical annexes contain generated
references to the schema, permissions, routes, configuration and invariant tests.

For persistent domain changes, start with the business invariant and the existing
[database schema](docs/architecture/A2-manager-contracts.md#control-plane-sql-catalogue):
entities, ownership, relationships, constraints and lifecycle. Then trace the
transaction and permission checks, API contract and user interaction.

From the repository root, with Make, Python 3 and Docker:

```bash
make -C docs/architecture generate
make -C docs/architecture check
```

Generation refreshes technical references. These checks do not execute the
referenced tests or validate user journeys or handwritten prose.

Historical RFCs, Swift documentation and the previous OpenSpec corpus are
available in Git history. They are not current implementation contracts. A future
increment may introduce a focused OpenSpec change when its scope requires one.
Component READMEs retain local commands and usage details; architectural
explanations belong in the dossier.

## Contributions and releases

Describe the problem, changed behavior and validation in the pull request.
Update the relevant architecture explanation when behavior changes. Record
operator impact using the [release-note workflow](deploy/release-notes/README.md).
Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Fred's own code is licensed under [Apache 2.0](LICENSE).
Third-party dependencies retain their own licenses and notices. Package metadata,
lockfiles and build inventories identify the dependencies of each component.
The optional PyMuPDF installation is described in the
[Knowledge Flow README](apps/knowledge-flow-backend/README.md#optional-pymupdf-processing).

## Community

- [Project website](https://site.fredlab.dev)
- [Discord](https://discord.gg/FDSEvNarG)
- Contact: <dimitri.tombroff@thalesgroup.com>
