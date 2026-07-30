"""Generate a synthetic manifest.json + users.json bundle for local OpenFGA/teams-list
scale testing (see `make build-load-test-bundle`).

This is NOT the curated demo fixture (`tests/fixtures/import_export/demo_provisioning/`,
tracked in git and consumed by `test_import_export_users.py`) — it produces a much larger,
throwaway bundle into a git-ignored `target/` directory.

Usernames must already exist as Keycloak identities (e.g. created via
fred-deployment-factory's `swify-add-user.sh --count N --prefix <prefix>`, using the same
`--prefix`/count here) — this script only describes team/role assignments for the Swift
import; it never talks to Keycloak or OpenFGA itself.

Every team referenced in users.json that doesn't already exist must have at least one
`team_admin` in the same bundle, or the whole import aborts before writing anything
(control_plane_backend/import_export/importer.py::_provision_bundle_teams). This generator
always seeds exactly one forced team_admin per team before scattering any other membership.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

TEAM_ROLES = ["team_member", "team_editor", "team_analyst"]


def build_users(
    num_users: int,
    num_teams: int,
    prefix: str,
    team_prefix: str,
    avg_teams_per_user: float,
    seed: int,
) -> tuple[list[dict], list[str]]:
    rng = random.Random(seed)
    user_width = len(str(num_users))
    team_width = len(str(num_teams))
    usernames = [f"{prefix}{i:0{user_width}d}" for i in range(1, num_users + 1)]
    teams = [f"{team_prefix}{i:0{team_width}d}" for i in range(1, num_teams + 1)]

    assignments: dict[str, dict[str, set[str]]] = {u: {} for u in usernames}

    # Every team needs a distinct team_admin seed, or the import rejects the whole
    # to-create team set before writing anything (see module docstring).
    for team, admin in zip(teams, rng.sample(usernames, k=num_teams)):
        assignments[admin].setdefault(team, set()).add("team_admin")

    extra_memberships = max(int(num_users * avg_teams_per_user) - num_teams, 0)
    for _ in range(extra_memberships):
        user = rng.choice(usernames)
        team = rng.choice(teams)
        role = rng.choice(TEAM_ROLES)
        assignments[user].setdefault(team, set()).add(role)

    users = []
    for username in usernames:
        team_roles: dict[str, list[str]] = {}
        for team, roles in assignments[username].items():
            for role in roles:
                team_roles.setdefault(role, []).append(team)
        users.append(
            {
                "username": username,
                "email": f"{username}@app.com",
                "first_name": username[0].upper() + username[1:],
                "last_name": "Swify",
                "password": "Azerty123_",  # pragma: allowlist secret — synthetic load-test fixture, not a real credential
                "teams": sorted(assignments[username].keys()),
                "team_roles": {
                    role: sorted(names) for role, names in team_roles.items()
                },
                "platform_roles": [],
            }
        )
    return users, teams


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--users", type=int, default=3000, help="number of user entries (default: 3000)"
    )
    parser.add_argument(
        "--teams", type=int, default=100, help="number of teams (default: 100)"
    )
    parser.add_argument(
        "--prefix",
        default="user",
        help="username prefix, must match Keycloak (default: user)",
    )
    parser.add_argument(
        "--team-prefix", default="team", help="team name prefix (default: team)"
    )
    parser.add_argument(
        "--avg-teams-per-user",
        type=float,
        default=1.3,
        help="target average team memberships per user (default: 1.3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="random seed, for reproducible bundles (default: 42)",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("target/load_test_provisioning")
    )
    args = parser.parse_args()

    if args.teams > args.users:
        parser.error(
            "--teams cannot exceed --users (each team needs a distinct team_admin)"
        )

    users, teams = build_users(
        args.users,
        args.teams,
        args.prefix,
        args.team_prefix,
        args.avg_teams_per_user,
        args.seed,
    )

    manifest = {
        "format_version": 1,
        "users_schema_version": 1,
        "source_platform": "swift",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "tuple_count": 0,
        "realm_exported": False,
        "content_keys": [],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.out_dir / "users.json").write_text(json.dumps(users, indent=2) + "\n")

    membership_count = sum(len(u["teams"]) for u in users)
    print(
        f"Generated {len(users)} users / {len(teams)} teams / {membership_count} team memberships "
        f"-> {args.out_dir}"
    )


if __name__ == "__main__":
    main()
