# Compatibility matrix

Each release publishes `compatibility-matrix.yaml`. The file lists the server versions
the release is compatible with: PostgreSQL, Keycloak, OpenSearch, and so on. A
deployment repository checks its own blueprint against this file. The file says nothing
about what is deployed where.

The matrix is attached to:

- the `code/vX.Y.Z` and `chart/vX.Y.Z` GitHub Releases;
- the `oci://ghcr.io/thalesgroup/fred-helm/fred:X.Y.Z` chart, as an OCI referrer of
  artifact type `application/vnd.fred.compatibility-matrix.v1+yaml`.

```bash
gh release download code/v3.18.0 --repo ThalesGroup/fred --pattern compatibility-matrix.yaml
oras discover ghcr.io/thalesgroup/fred-helm/fred:3.18.0
```

## How it is derived

Nobody writes server versions by hand. They come from two inputs:

| Input | Content | Maintained by |
| --- | --- | --- |
| `apps/*/uv.lock` | the client libraries each component locks (`opensearch-py` 2.8.0, `psycopg` 3.3.6...) | dependency updates, as today |
| [`clients.yaml`](clients.yaml) | for each client version range, the server versions its maintainers support, with the source | whoever bumps a client beyond the table |

For each service, the matrix keeps what every locked client of that service supports.
A checker branches on `support`:

```yaml
services:
  postgres:
    support: range            # compatible when min <= version < below
    min: 10.0.0
    below: 19.0.0             # absent: no published cap
    range: '>=10.0.0 <19.0.0' # the same bounds, for people and Masterminds or npm semver
    clients: [...]
  s3:
    support: any              # any conforming service (an API such as S3, a managed service)
    clients: [...]
  temporal:
    support: unknown          # a client of it publishes no server compatibility: report it as unverified
    clients: [...]
```

`clients` explains the result. It lists each locked client version, the components using
it, the server versions it supports and the source of that rule. A checker can ignore it.

The service names form a closed vocabulary, defined in
[`schemas/client-compatibility.schema.json`](schemas/client-compatibility.schema.json).
Consumers match on these names. Adding a service is a compatible change. Renaming or
removing one breaks consumers and needs a new `apiVersion`.

## Bumping a client

The `Check compatibility matrix` workflow fails when a locked client version falls
outside every rule of `clients.yaml`, for example `opensearch-py` 3.0.0. To fix it:

1. find the compatibility statement of the client's maintainers;
2. add a rule for the new client range in `clients.yaml`, with its `source`;
3. remove the rules no locked version matches any more (the check reports them).

A range is narrower when Fred depends on a client feature that needs a newer server.
Write that in the rule's `note`; the OpenFGA rule is an example.

## Commands

```bash
make compatibility-matrix         # print the matrix this checkout derives
make compatibility-matrix-tests   # test the derivation offline
```

Both release workflows run `scripts/compatibility_matrix.py build`. The output depends
only on the tagged commit, so the code release and the chart release publish the same
file.
