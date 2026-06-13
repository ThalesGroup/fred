# Keycloak identity bootstrap for S3NS — platform prerequisite for the Kea→Swift migration

**Audience:** Sébastien (ops/platform lead) and anyone standing up the S3NS environment.
**Owner of this task:** platform/ops — **not** the application migration team.
**Status:** prerequisite. Must be **fully completed and verified** before any application
data (Postgres `fred_kea`, OpenFGA tuples) is imported into S3NS.
**Backlog:** `MIGR-04` in [`KEA-MIGRATION-BACKLOG.md`](../backlog/KEA-MIGRATION-BACKLOG.md).
**Related design:** [`PERSONAL-TEAM-ISOLATION-RFC.md`](../rfc/PERSONAL-TEAM-ISOLATION-RFC.md),
[`TASK-EVENT-STREAM-RFC.md`](../rfc/TASK-EVENT-STREAM-RFC.md) (the data-migration steps that
**assume** this prerequisite is met).
**Keycloak version in scope:** 26.3.0 (Quarkus distribution).

---

## 1. Why this is the first migration step (the one-paragraph version)

Fred identifies every user by the Keycloak **`sub`** claim — a UUID minted by Keycloak. That
UUID is the **join key** for everything the application owns: agent ownership, conversation
ownership, team memberships, and every OpenFGA authorization tuple (`user:<uuid>`). The
corporate SSO does **not** provide this UUID; Keycloak generates it locally the first time it
sees a user. Therefore a **fresh** S3NS Keycloak will mint **new, different** UUIDs for the
same people — and the moment that happens, all imported application data points at UUIDs that
no longer exist. Every user is orphaned: they log in and see an empty account.

**The platform must guarantee that each user keeps the same `sub` on S3NS that they had
on-premise.** This is achieved by exporting the on-prem Keycloak users **with their `id`** and
importing them into S3NS **before** anyone logs in — not by relying on SSO brokering, which by
itself preserves nothing.

> Mental model: the corporate SSO is the user's **passport** (same everywhere). The Keycloak
> `sub` is a **locker number** the local Keycloak assigns. The application stores everyone's
> belongings *by locker number*. A fresh S3NS Keycloak hands out new locker numbers unless we
> explicitly carry the old ones over.

---

## 2. What the platform must guarantee (acceptance criteria)

The S3NS Keycloak is considered correctly bootstrapped when **all** of the following hold,
**before** any application data import:

1. **Same realm name** as on-prem (`app`), and the same **client** definitions the apps expect.
2. **Every on-prem user exists on S3NS with the identical `id` (UUID).** No new UUIDs.
3. **The corporate-SSO identity provider (IdP) is configured with the same `alias`** as on-prem,
   so the federated-identity links resolve.
4. **First brokered login attaches to the pre-existing user** (via the imported
   `federatedIdentities`, or by email-based account linking) — it must **not** create a new user.
5. The **strategy is "preserve", never "remap".** We do not generate new UUIDs and translate
   them in the data. (Remapping would invalidate the application team's local rehearsal and is
   far more error-prone.)

If any of these is not met, **stop** — importing application data on top of it will orphan users.

---

## 3. Procedure

### Step A — Export from on-prem Keycloak (captures UUIDs + SSO links)

Run a realm export. This produces JSON containing the `users` array, where each user object
carries its `id` (the UUID) **and** its `federatedIdentities` (the SSO link).

```bash
# inside the on-prem keycloak container (or a one-off container against the same DB)
/opt/keycloak/bin/kc.sh export \
  --dir /tmp/kc-export --realm app --users realm_file
# then copy /tmp/kc-export/app-realm.json off the container
```

> Run during a quiet window — the export reads the live database and you want a consistent
> snapshot. Treat the export file as **sensitive** (it contains the full user directory).

### Step B — Stand up the S3NS Keycloak realm with the corporate SSO broker

Create the `app` realm on S3NS and configure the corporate-SSO IdP **with the same `alias`**
used on-prem. Do this **before** loading users, and do **not** import the whole on-prem realm
file over it (that would overwrite the broker config). Users are loaded surgically in Step C.

### Step C — Import users only, preserving the UUID

Use the **`partialImport`** admin endpoint, which preserves the `id` from the JSON and leaves
the rest of the realm (clients, broker config) untouched.

```bash
# admin token on S3NS
TOKEN=$(curl -s -X POST \
  "$S3NS_KC/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli \
  -d username="$KC_ADMIN" -d password="$KC_ADMIN_PW" | jq -r .access_token)

# take only the users array from the export and push it
jq '{ifResourceExists:"SKIP", users:.users}' app-realm.json > users-import.json

curl -s -X POST "$S3NS_KC/admin/realms/app/partialImport" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data @users-import.json | jq .
```

`partialImport` keeps the `id`. After this, S3NS Keycloak holds every user with their original
UUID, waiting for them to authenticate via SSO.

### Step D — Ensure first login links, does not create

Two ways, in order of preference:

1. **Preferred — preserved `federatedIdentities`.** If the on-prem export included each user's
   `federatedIdentities` (it does, with `--users realm_file`) **and** the S3NS IdP `alias`
   matches on-prem, the link is already in place: first login resolves to the existing user
   automatically, no prompts.
2. **Fallback — email-based account linking.** If links cannot be preserved or the alias
   differs, configure the realm's *first broker login* flow to match the brokered identity to an
   existing local user **by email** and link automatically. (Relies on email being present and
   unique.)

---

## 4. Acceptance test — prove it with ONE user before trusting all of them

Pick a real user (e.g. `francoise@thalesgroup.com`):

```bash
# 1. on-prem: record her UUID (admin console → Users → her → "ID")
ONPREM_ID=...        # e.g. a1b2c3d4-...

# 2. on S3NS after Step C: the same UUID must be present
curl -s -H "Authorization: Bearer $TOKEN" \
  "$S3NS_KC/admin/realms/app/users?email=francoise@thalesgroup.com" | jq -r '.[].id'
#    → MUST print the same a1b2c3d4-...

# 3. have her log in via SSO; decode the issued token and check:
#    sub == a1b2c3d4-...   ✅ bootstrap is correct
#    sub != a1b2c3d4-...   ❌ users are being recreated — DO NOT proceed to data import
```

Green on all three → the platform is ready and the application data import can proceed safely.

---

## 5. What happens if this is skipped (the failure mode, explicitly)

If application data is imported onto a Keycloak that mints new UUIDs:

- Every user logs in as a **brand-new person** (new `sub`).
- They see only an **empty personal team**; none of their agents, conversations, or permissions
  appear (those belong to the old UUID).
- OpenFGA tuples reference UUIDs that **no human can ever authenticate as** → permanent orphans.
- There is **no clean in-place repair** afterwards short of a remap-and-rewrite of every table
  and every tuple. It is far cheaper to get the bootstrap right up front.

---

## 6. Handoff contract with the application migration team

This division of responsibility lets the two workstreams proceed independently:

| Responsibility | Owner | Covered by |
| --- | --- | --- |
| Keycloak realm + users + SSO broker on S3NS, **UUIDs preserved** | **Platform/ops (this doc)** | §2–§4 above |
| Postgres `fred_kea` data, OpenFGA tuples, buckets/indices import | Application migration team | `MIGR-02`, `TASK-EVENT-STREAM-RFC` |

**The application team works under the firm assumption that §2 is fully satisfied.** Locally,
they rehearse the data migration with kea and swift pointing at a **single shared Keycloak**,
which is a faithful model of the *post-bootstrap* production state (one stable `sub` per user,
seen identically by both sides). The only thing that local rehearsal does **not** exercise is
this bootstrap itself — which is precisely why it is owned here, by the platform.
