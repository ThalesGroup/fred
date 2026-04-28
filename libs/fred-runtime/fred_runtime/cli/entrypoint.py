from __future__ import annotations

import argparse
import getpass
import os
import uuid
from collections.abc import Sequence

import httpx
from fred_core.cli.auth import (
    KeycloakUserSessionManager,
    build_cli_token_provider,
    default_configuration_file,
    default_keycloak_token_file,
    default_pkce_callback_host,
    default_pkce_callback_port,
    load_cli_environment,
    resolve_keycloak_login_config,
)
from fred_core.cli.ui import colors_enabled

from .history_display import run_single_turn
from .pod_client import AgentPodClient
from .repl import run_interactive_chat
from .url_helpers import (
    default_agent_metrics_url,
    default_agent_pod_base_url,
    normalize_base_url,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the chat client."""
    parser = argparse.ArgumentParser(description="Chat with a running Fred agent pod.")
    parser.add_argument(
        "--base-url",
        default=default_agent_pod_base_url(),
        help="Pod base URL. Defaults to app.port + app.base_url from configuration.yaml.",
    )
    parser.add_argument(
        "--metrics-url",
        default=None,
        help=(
            "Prometheus metrics URL used by /kpi. Defaults to app.metrics_port "
            "from configuration.yaml when available."
        ),
    )
    parser.add_argument(
        "--agent",
        default=None,
        help="Optional agent id. Defaults to the first registered agent.",
    )
    parser.add_argument(
        "--session-id",
        default=f"dev-session-{uuid.uuid4().hex[:8]}",
        help="Session id sent to the pod for multi-turn state.",
    )
    parser.add_argument(
        "--user-id",
        default=getpass.getuser(),
        help="User id sent to the pod context.",
    )
    parser.add_argument(
        "--team-id",
        default=os.getenv("FRED_AGENT_TEAM_ID"),
        help="Optional team id sent to the pod context for team-scoped execution.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser-based Keycloak PKCE login before sending requests.",
    )
    parser.add_argument(
        "--login-password",
        action="store_true",
        help="Use direct username/password login as a local fallback.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("FRED_AGENT_USERNAME"),
        help="Optional default username used by `--login-password` and `/login-password`.",
    )
    parser.add_argument(
        "--keycloak-realm-url",
        default=os.getenv("FRED_AGENT_KEYCLOAK_REALM_URL"),
        help="Optional Keycloak realm URL for CLI login discovery.",
    )
    parser.add_argument(
        "--keycloak-client-id",
        default=os.getenv("FRED_AGENT_KEYCLOAK_CLIENT_ID"),
        help="Optional Keycloak client id for CLI login discovery.",
    )
    parser.add_argument(
        "--keycloak-client-secret",
        default=os.getenv("FRED_AGENT_KEYCLOAK_CLIENT_SECRET"),
        help="Optional Keycloak client secret for confidential login clients.",
    )
    parser.add_argument(
        "--keycloak-callback-host",
        default=default_pkce_callback_host(),
        help="Loopback host used for browser PKCE login callbacks.",
    )
    parser.add_argument(
        "--keycloak-callback-port",
        type=int,
        default=default_pkce_callback_port(),
        help="Loopback port used for browser PKCE login callbacks.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print intermediate runtime events in addition to the final answer.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use the SSE endpoint and render events live as they arrive.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI terminal colors in the chat client output.",
    )
    parser.add_argument(
        "message",
        nargs="*",
        help="Optional one-shot message. Omit it to start interactive mode.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Fred agent pod chat client."""
    env_file = load_cli_environment(log_prefix="[CLI CONFIG]")
    parser = build_parser()
    args = parser.parse_args(argv)
    base_url = normalize_base_url(args.base_url)
    metrics_url = (
        args.metrics_url.rstrip("/")
        if args.metrics_url
        else default_agent_metrics_url(base_url=base_url)
    )
    color_enabled = colors_enabled(no_color=args.no_color)

    config_file = default_configuration_file()
    print(f"[cli] env file  : {env_file}")
    print(f"[cli] config    : {config_file} (exists={config_file.exists()})")
    print(f"[cli] pod url   : {base_url}")
    print(f"[cli] metrics   : {metrics_url or 'not configured'}")

    http_client = httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0, read=None))
    auth_session = None
    login_config = resolve_keycloak_login_config(
        realm_url=args.keycloak_realm_url,
        client_id=args.keycloak_client_id,
        client_secret=args.keycloak_client_secret,
    )
    if login_config is not None:
        print(
            f"[cli] auth      : keycloak realm={login_config.realm_url}"
            f"  client={login_config.client_id}"
        )
        auth_session = KeycloakUserSessionManager(
            config=login_config,
            cache_file=default_keycloak_token_file(),
            log_prefix="[cli]",
        )
    else:
        print("[cli] auth      : none  (standalone mode — security disabled)")

    effective_team_id = args.team_id or ("personal" if login_config is None else None)
    if effective_team_id:
        print(f"[cli] team      : {effective_team_id}")

    static_token = os.getenv("FRED_AGENT_TOKEN")

    client = AgentPodClient(
        base_url=base_url,
        http_client=http_client,
        metrics_url=metrics_url,
        token_provider=build_cli_token_provider(
            auth_session=auth_session,
            static_token=static_token,
            log_prefix="[cli]",
        )
        if auth_session is not None or static_token
        else None,
    )

    try:
        if args.login and args.login_password:
            print("Choose only one login mode: `--login` or `--login-password`.")
            return 1
        if args.login:
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings with "
                    "`--keycloak-realm-url` and `--keycloak-client-id`, or run "
                    "from a pod project with configuration.yaml."
                )
                return 1
            auth_session.login_with_pkce(
                callback_host=args.keycloak_callback_host,
                callback_port=args.keycloak_callback_port,
            )
            print(f"Logged in as {auth_session.current_username()}.")
        if args.login_password:
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings with "
                    "`--keycloak-realm-url` and `--keycloak-client-id`, or run "
                    "from a pod project with configuration.yaml."
                )
                return 1
            username = args.username or input("Username: ").strip()
            if not username:
                print("Username cannot be empty.")
                return 1
            password = getpass.getpass("Password: ")
            auth_session.login(username=username, password=password)
            print(f"Logged in as {auth_session.current_username()}.")
        if args.message:
            agents = client.list_agents()
            active_agent = args.agent or agents[0]
            exit_code, _ = run_single_turn(
                client=client,
                agent_id=active_agent,
                message=" ".join(args.message),
                session_id=args.session_id,
                user_id=args.user_id,
                team_id=effective_team_id,
                verbose=args.verbose,
                stream=args.stream,
                color_enabled=color_enabled,
            )
            return exit_code
        return run_interactive_chat(
            client=client,
            agent_id=args.agent,
            session_id=args.session_id,
            user_id=args.user_id,
            team_id=effective_team_id,
            verbose=args.verbose,
            stream=args.stream,
            color_enabled=color_enabled,
            auth_session=auth_session,
            callback_host=args.keycloak_callback_host,
            callback_port=args.keycloak_callback_port,
        )
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}")
        return 1
    finally:
        http_client.close()
        if auth_session is not None:
            auth_session.close()
