# Verification

- Existing local Swift deployment: 3 team rows retained exactly (plus organization_id=fred), all 21 existing FGA tuples retained, both platform administrators gained organization_admin. Organization/team permissions and SQL state unchanged after a second Control Plane startup. No saved prompt existed in this deployment.
- Isolated PostgreSQL upgrade: historical migrations to a3f7c9e2d514, legacy team and saved prompt insertion, upgrade, repeated upgrade, downgrade and upgrade passed; original prompt text preserved. Temporary database removed.
- Isolated real OpenFGA store: compiled model accepted; 16 checks cover platform/org role separation, scoped prompt access, public discovery isolation and protected content. Store removed.
- Generated contracts: make update-control-plane-api completed; schema.fga.json regenerated with the installed official OpenFGA CLI via make transform-openfga-schema.
- Repository-wide checks were explicitly delegated by the developer: both make test and make code-quality passed from the repository root.
- Explicit organization membership and default-fred onboarding resolve the reviewed self-join bypass: can_join checks organization membership before writing a team role. Existing team-derived membership is persisted independently on onboarding.
- Targeted regression run: 254 passed with two stale registry fixtures subsequently corrected; rerun of the whole registry file plus new HTTP lifecycle/isolation tests: 39 passed. The original eight reported failures are resolved; the final whole-repository run is recorded below.
- Independent review: prompt lookup remains async, no new blocking I/O or cache; prior registry-discovery, import identity, deletion-race and candidate-route findings addressed. Personal-library sharing remains a pre-existing surface without organization ownership and is not proven tenant isolation by this change.
- Membership/CGU targeted regressions: 34 passed (organization stores/routes, global CGU/default-team behavior and self-joining). Includes newcomer, preassigned user, membership surviving last-team departure, scoped member assignment and default-team filtering.
- CGU storage and configured version remain global. No per-organization consent field, migration or reset introduced.
- Core CGU admission/ReBAC regressions: 40 passed. Team role/charter invitation regressions: 45 passed, plus 4 targeted HTTP cases. Team-admin invitations and role grants now require the recipient's existing organization membership; they cannot admit outsiders.
- Final root make test passed after the fixture/type corrections and frontend permission-map update. Root make code-quality passed; no baseline relaxation or nosec suppression was added.

Final logs: `/tmp/fred-organizations-make-test-final.log` and `/tmp/fred-organizations-code-quality.log`. Fixes from these runs: seed the default organization in the core team fixture, use typed SQLAlchemy insert/table APIs in test fixtures, narrow nullable test values and test-double types, and map generated `can_join` to the existing frontend permission flag mechanism with coverage. No UI screen or workflow changes.
