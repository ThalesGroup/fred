# /// script
# dependencies = [
#   "pyyaml>=6.0",
#   "python-dotenv>=1.0",
# ]
# ///
"""Prepare local delegation without modifying tracked YAML files.

Run after deployment-factory's make docker-up, before starting Fred:
    make delegation
    make delegation ARGS=--dry-run
    make delegation ARGS=--reset

Uses the existing agentic client credentials, never Keycloak admin credentials,
and checks that the minted token satisfies each application's delegation block:
the delegation caller role at the configured claim, the delegation audience, a
realm issuer and, where a block sets service_accounts_only, the service-account
markers. Writes config/.delegation.local.json for the three applications; each
switches on one direction of that application's own YAML delegation block,
act_for_people for the caller and accept_delegated_calls for the receivers, and
keeps every other setting. Local make run and make run-worker load it; rerun after recreating
the Keycloak realm or changing a delegation setting the token must satisfy.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
APPS = ("control-plane-backend", "knowledge-flow-backend", "fred-agents")
CALLER_APP = "fred-agents"
CONFIG = "config/configuration_prod.yaml"
# Keep in step with fred_pod.security.delegation.DelegationConfig's defaults.
DEFAULT_AUDIENCE = "fred-delegation"
DEFAULT_CALLER_ROLE = "delegation_caller"


def fail(message: str) -> None:
    sys.exit(f"error: {message}")


def read_env_value(env_file: Path, name: str) -> str | None:
    """Read one KEY=VALUE from a dotenv file without exporting anything."""
    if name in os.environ:
        return os.environ[name]
    return dotenv_values(env_file).get(name)


def decode_claims(token: str) -> dict:
    """Read a JWT's claims; the receivers verify the signature, not this script."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError) as exc:
        raise ValueError("the token endpoint did not return a JWT") from exc


def mint_claims(realm_url: str, client_id: str, secret: str) -> dict:
    url = f"{realm_url.rstrip('/')}/protocol/openid-connect/token"
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        fail(f"the realm URL must be http or https, got {realm_url}")
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        }
    ).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            token = json.load(response)["access_token"]
    except urllib.error.HTTPError as exc:
        reason = ""
        try:
            reason = json.load(exc).get("error", "")
        except ValueError:
            pass
        fail(
            f"Keycloak refused the {client_id} client credentials (HTTP {exc.code} {reason})."
        )
    except urllib.error.URLError as exc:
        fail(
            f"cannot reach {url}: {exc.reason}. Is the local Keycloak running and its host resolvable?"
        )
    return decode_claims(token)


def claim_at(claims: dict, path: list[str]) -> object:
    value: object = claims
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def bears_service_account_markers(claims: dict, client_id: str) -> bool:
    """Keep in step with fred_core.security.delegation.bears_service_account_markers."""
    username = claims.get("preferred_username")
    named = claims.get("client_id", claims.get("clientId"))
    return (
        isinstance(username, str)
        and username.lower() == f"service-account-{client_id}".lower()
        and named == client_id
    )


def delegation_block(config: dict) -> dict:
    return dict((config.get("security") or {}).get("delegation") or {})


def token_problems(claims: dict, configs: dict[str, dict], client_id: str) -> list[str]:
    """Name each application whose delegation settings this token does not satisfy."""
    audiences = claims.get("aud") or []
    audiences = [audiences] if isinstance(audiences, str) else list(audiences)
    problems = []
    for app in APPS:
        security = configs[app].get("security") or {}
        delegation = delegation_block(configs[app])
        audience = delegation.get("audience") or DEFAULT_AUDIENCE
        role = delegation.get("caller_role") or DEFAULT_CALLER_ROLE
        path = delegation.get("caller_roles_claim") or [
            "resource_access",
            audience,
            "roles",
        ]
        roles = claim_at(claims, list(path))
        if not isinstance(roles, list) or role not in roles:
            problems.append(
                f"{app} expects role '{role}' at '{'.'.join(path)}': "
                f"grant it to {client_id}'s service account"
            )
        if audience not in audiences:
            problems.append(f"{app} expects '{audience}' in the token audience")
        if delegation.get(
            "service_accounts_only"
        ) and not bears_service_account_markers(claims, client_id):
            problems.append(
                f"{app} trusts service-account tokens only: the token lacks "
                f"preferred_username service-account-{client_id} or the client_id claim"
            )
        issuers = {
            str((security.get(block) or {}).get("realm_url", "")).rstrip("/")
            for block in ("user", "m2m")
        } - {""}
        if issuers and str(claims.get("iss", "")).rstrip("/") not in issuers:
            problems.append(
                f"{app} expects an issuer in {sorted(issuers)}, "
                f"the token says {claims.get('iss')}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="check and report, write nothing"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="remove the generated files; the YAML settings apply again",
    )
    args = parser.parse_args()

    paths = [ROOT / "apps" / app / "config/.delegation.local.json" for app in APPS]
    if args.reset:
        for path in paths:
            if not args.dry_run:
                path.unlink(missing_ok=True)
            print(
                f"{path.relative_to(ROOT)}: {'would remove' if args.dry_run else 'removed'}"
            )
        return 0

    configs = {
        app: yaml.safe_load((ROOT / "apps" / app / CONFIG).read_text()) or {}
        for app in APPS
    }
    for app in APPS:
        selected = (
            read_env_value(ROOT / "apps" / app / "config/.env", "CONFIG_FILE")
            or "./config/configuration.yaml"
        )
        if (ROOT / "apps" / app / selected).resolve() != (
            ROOT / "apps" / app / CONFIG
        ).resolve():
            fail(
                f"{app}: set CONFIG_FILE=./config/configuration_prod.yaml in config/.env before preparing delegation"
            )
    m2m = (configs[CALLER_APP].get("security") or {}).get("m2m") or {}
    client_id, realm_url, secret_var = (
        m2m.get("client_id"),
        m2m.get("realm_url"),
        m2m.get("secret_env_var"),
    )
    if not (client_id and realm_url and secret_var):
        fail(f"apps/{CALLER_APP}/{CONFIG} has no complete security.m2m block")
    secret = read_env_value(ROOT / "apps" / CALLER_APP / "config/.env", secret_var)
    if not secret:
        fail(
            f"{secret_var} is neither exported nor set in apps/{CALLER_APP}/config/.env"
        )
    claims = mint_claims(str(realm_url), client_id, secret)
    if claims.get("azp") != client_id:
        fail("the workload token must identify the configured client")
    problems = token_problems(claims, configs, client_id)
    if problems:
        for problem in problems:
            print(f"  - {problem}")
        fail(
            "delegation configuration not written: fix the caller role, audience or issuer first"
        )
    for app, path in zip(APPS, paths):
        payload = {
            "issuer": claims["iss"],
            "audiences": claims["aud"],
            "delegation": (
                {"act_for_people": True}
                if app == CALLER_APP
                else {"accept_delegated_calls": True}
            ),
        }
        if not args.dry_run:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2) + "\n")
            temporary.replace(path)
        print(
            f"{path.relative_to(ROOT)}: {'would prepare' if args.dry_run else 'prepared'}"
        )
    print(
        "Tracked YAML files unchanged. Start Control Plane first, then bootstrap the admin and import the demo bundle."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
