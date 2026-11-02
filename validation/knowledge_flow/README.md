# Knowledge Flow cross-component contracts

These existing scenarios produce CSV/Excel artifacts with the worker and read them through the API's DuckDB/HTTP services. They deliberately install neither application as a dependency of the other. Application-specific suites and isolated-installation checks remain separate.

From the repository root, run `make test-knowledge-flow-contracts`. This target prepares the worker environment, then uses both applications’ sources for this explicit cross-component test only. No test is run as part of E1 authoring.
