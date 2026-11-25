# `validation/`

Cross-component material that belongs to no single application:

- [`knowledge_flow/`](knowledge_flow/README.md): Knowledge Flow worker/API
  contracts. Run them from the repository root with
  `make test-knowledge-flow-contracts`.
- [`fixtures/oidc_uid_vector.json`](fixtures/oidc_uid_vector.json): the shared OIDC
  user-identifier vector read by the fred-core and frontend authentication tests.

The black-box authorization suite that logged in as the demo users targeted the
Swift model (teams, `/knowledge-flow/v1` routes) and could not run against Weaver.
It was removed from this branch and remains on branch `swift`. A Weaver
equivalent must be written against spaces and the Control Plane routes.
