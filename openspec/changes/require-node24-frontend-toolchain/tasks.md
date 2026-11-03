## 1. Align supported tooling

- [x] 1.1 Pin application/package CI, frontend Dockerfiles and Makefile tooling to Node 24.21.0/npm 11.19.0; verify actual versions and successful locked installs in both application and producer environments.
- [x] 1.2 Declare >=24.21.0 <25 in application, producer and distributed package engines, enforce the range at repository install/build entry points and regenerate affected locks; verify metadata consistency and rejection of Node 22, Node 24 below the minimum and Node 25 before dependency installation/build.
- [x] 1.3 Update release/application contracts and successful evidence fixtures while preserving immutable archive transfer; verify release-contract, CI selection and fixture/evidence tests.

## 2. Verify and document compatibility

- [x] 2.1 Update active setup/release documentation and the migration note; verify no active instruction advertises Node 22 support and run `make migration-check`.
- [ ] 2.2 Run the root `make code-quality` once for the completed change and full application/producer test and build targets under the selected tooling; validate all three actual packed archives, isolated consumers, browser checks and packed SDK production-host integration, including the exact dependency graph from #3298.
- [ ] 2.3 Apply the full branch audit and independent review against swift, disposition findings and record base/head and verification in the PR; reconcile, sync and archive this OpenSpec change when implementation verification is complete.
