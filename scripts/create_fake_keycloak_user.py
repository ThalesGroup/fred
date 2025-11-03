#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "python-keycloak>=5.8.1",
# ]
# ///
from __future__ import annotations

import argparse
import random
import string

from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError, KeycloakPostError

FAKE_FIRST_NAMES: list[str] = [
    "Camille",
    "Julien",
    "Claire",
    "Louis",
    "Elise",
    "Hugo",
    "Manon",
    "Theo",
    "Lucie",
    "Bastien",
    "Adele",
    "Armand",
    "Brigitte",
    "Cedric",
    "Estelle",
    "Gaspard",
    "Helene",
    "Lena",
    "Matthieu",
    "Nicolas",
    "Oceane",
    "Pascal",
    "Sabine",
    "Sylvie",
    "Tristan",
    "Valerie",
    "Yves",
    "Zoe",
]

FAKE_LAST_NAMES: list[str] = [
    "Dubois",
    "Lefevre",
    "Moreau",
    "Laurent",
    "Roussel",
    "Mercier",
    "Blanc",
    "Robin",
    "Fontaine",
    "Garnier",
    "Chevalier",
    "Collet",
    "Deschamps",
    "Fleury",
    "Gaillard",
    "Lambert",
    "Marchand",
    "Noel",
    "Perrin",
    "Renard",
    "Riviere",
    "Roche",
    "Tessier",
    "Valentin",
    "Vidal",
    "Voisin",
    "Perrot",
    "Barbier",
]


def _generate_username(first: str, last: str, existing: set[str]) -> str:
    while True:
        suffix = "".join(random.choices(string.digits, k=3))
        username = f"{first.lower()}.{last.lower()}{suffix}"
        if username not in existing:
            return username


def _generate_password() -> str:
    return ""


def create_fake_users(number_users: int = 10) -> None:
    admin = KeycloakAdmin(
        username="admin",
        password="",
        server_url="http://app-keycloak:8080/",
        realm_name="app",
        user_realm_name="master",
    )

    app_client_id = admin.get_client_id("app")
    if app_client_id is None:
        raise RuntimeError("Client 'app' not found in Keycloak realm.")

    editor_role = admin.get_client_role(client_id=app_client_id, role_name="editor")

    created_users: list[tuple[str, str]] = []
    failed_users: list[str] = []

    existing_usernames: set[str] = set()

    for _ in range(number_users):
        first_name = random.choice(FAKE_FIRST_NAMES)
        last_name = random.choice(FAKE_LAST_NAMES)
        username = _generate_username(first_name, last_name, existing_usernames)
        existing_usernames.add(username)
        email = f"{username}@example.com"
        password = _generate_password()

        user_representation = {
            "username": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": True,
        }

        try:
            admin.create_user(user_representation)
        except KeycloakPostError as exc:
            if exc.response_code == 409:
                user_id = admin.get_user_id(username)
            else:
                failed_users.append(username)
                continue
        else:
            user_id = admin.get_user_id(username)

        if not user_id:
            failed_users.append(username)
            continue

        try:
            admin.set_user_password(user_id=user_id, password=password, temporary=False)
        except (KeycloakGetError, KeycloakPostError):
            failed_users.append(username)
            continue

        if editor_role:
            try:
                admin.assign_client_role(
                    user_id=user_id,
                    client_id=app_client_id,
                    roles=[editor_role],
                )
            except (KeycloakGetError, KeycloakPostError):
                print(f"Warning: failed to assign 'editor' role to {username}.")
        created_users.append((username, password))

    if created_users:
        print("Created users:")
        for username, password in created_users:
            print(f"  - {username} / {password}")

    if failed_users:
        print("Users that failed to create:")
        for username in failed_users:
            print(f"  - {username}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create fake Keycloak users.")
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="Number of fake users to create (default: 10).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    create_fake_users(number_users=args.count)
