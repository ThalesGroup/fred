# Jira skill — setup

Only read this when something in `SKILL.md` fails: `acli` is missing, auth is broken, or
`jira.py` asks for a token. Nothing here is needed on a working machine.

## 1. Is `acli` installed and logged in?

```bash
command -v acli && acli jira auth status    # → site, email, auth type
```

## 2. Installing `acli`

You cannot install it for the developer (package managers need sudo). Read the guide for
**their** OS and relay the current commands — do not copy them into this file, they change:

- Index: <https://developer.atlassian.com/cloud/acli/guides/install-acli/>
- macOS: <https://developer.atlassian.com/cloud/acli/guides/install-macos/>
- Windows: <https://developer.atlassian.com/cloud/acli/guides/install-windows/>
- Linux: <https://developer.atlassian.com/cloud/acli/guides/install-linux/>

Fetch the page, then give them the commands to paste. In Claude Code they can run one
inline with `! <command>`.

## 3. Logging in

```bash
acli jira auth login      # interactive browser OAuth
```

Also not something you can do for them — suggest `! acli jira auth login`.

## 4. API token (downloads and comments only)

`acli` keeps its OAuth tokens in the OS keyring and offers no way to reuse them for REST
calls, so `jira.py attachments` and `jira.py comment` use Basic auth instead. `acli` cannot
mint a token either (`acli jira auth login --token` only *consumes* one) — the web UI is
the only way:

1. <https://id.atlassian.com/manage-profile/security/api-tokens> → create a token.
2. The developer pastes it into their own terminal (never through you):

   ```bash
   printf '%s' '<token>' > ~/.config/acli/api_token && chmod 600 ~/.config/acli/api_token
   ```

   `JIRA_API_TOKEN` in the environment works too.

Site and email are read from `acli`'s own config — nothing else to configure, and no need
to re-login `acli`; its OAuth session keeps serving every other command.
