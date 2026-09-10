#!/usr/bin/env python3
"""Helpers for the `jira` skill: the three things `acli` cannot do on its own.

`show`        renders an issue (description + comments) as Markdown. `acli jira workitem
              view` silently drops the description because it is Atlassian Document Format,
              not text -- this flattens ADF so the body is actually readable.
`attachments` lists and downloads attachments. `acli` has no download command at all, so
              screenshots on a ticket are otherwise unreachable.
`comment`     posts a comment as a JSM *internal note* (the default here) or as a public
              reply. `acli jira workitem comment create` always uses the project default
              visibility and cannot set the internal flag; only the REST comment property
              `sd.public.comment` can. Markdown in, ADF out, so headings and code blocks
              survive.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ACLI_CONFIG = Path.home() / ".config" / "acli" / "jira_config.yaml"
TOKEN_FILE = Path.home() / ".config" / "acli" / "api_token"

TOKEN_HELP = f"""No Jira API token found.

`acli` authenticates with OAuth tokens kept in the OS keyring, which cannot be reused for
plain REST calls -- so downloading attachments and posting internal notes need a personal
API token. `acli` cannot create one; only the web UI can:

  1. Create one at https://id.atlassian.com/manage-profile/security/api-tokens
  2. Store it:  printf '%s' '<token>' > {TOKEN_FILE} && chmod 600 {TOKEN_FILE}
     (or export JIRA_API_TOKEN=<token>)

Site and email are read from acli's own config, so there is nothing else to set up."""


# --------------------------------------------------------------------------- config


def acli_profile() -> dict:
    """Site + email of the acli profile currently logged in."""
    if not ACLI_CONFIG.exists():
        sys.exit(f"{ACLI_CONFIG} not found -- run `acli jira auth login` first.")
    text = ACLI_CONFIG.read_text(encoding="utf-8")
    try:
        import yaml

        cfg = yaml.safe_load(text)
        current = cfg.get("current_profile")
        profiles = cfg.get("profiles") or []
        for p in profiles:
            if f"{p.get('cloud_id')}:{p.get('account_id')}" == current:
                return p
        if profiles:
            return profiles[0]
    except ImportError:
        site = re.search(r"^\s*-?\s*site:\s*(\S+)", text, re.M)
        email = re.search(r"^\s*email:\s*(\S+)", text, re.M)
        if site and email:
            return {"site": site.group(1), "email": email.group(1)}
    sys.exit(f"Could not read a Jira profile from {ACLI_CONFIG} -- run `acli jira auth status`.")


def api_token() -> str:
    token = os.environ.get("JIRA_API_TOKEN")
    if not token and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        sys.exit(TOKEN_HELP)
    return token


class _StripAuthOnHostChange(urllib.request.HTTPRedirectHandler):
    """Jira redirects attachment content to a pre-signed media host; never forward creds there."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(
            req.full_url
        ).netloc:
            new.remove_header("Authorization")
        return new


def rest(url: str, profile: dict, payload: dict | None = None) -> bytes:
    """GET, or POST when `payload` is given, authenticating with email + API token."""
    creds = base64.b64encode(f"{profile['email']}:{api_token()}".encode()).decode()
    headers = {"Authorization": f"Basic {creds}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener(_StripAuthOnHostChange())
    try:
        with opener.open(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            sys.exit(f"{exc.code} from Jira -- the API token is missing, wrong or expired.\n\n{TOKEN_HELP}")
        detail = exc.read().decode("utf-8", "replace")[:500]
        sys.exit(f"{exc.code} {exc.reason} for {url}\n{detail}")


def acli_json(*args: str) -> dict:
    proc = subprocess.run(
        ["acli", "jira", "workitem", *args, "--json"], capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        sys.exit((proc.stderr or proc.stdout).strip() or "acli failed")
    return json.loads(proc.stdout)


# --------------------------------------------------------------------- ADF -> text


def adf_to_text(node, depth: int = 0) -> str:
    """Flatten an Atlassian Document Format node to Markdown-ish text."""
    if node is None:
        return ""
    if isinstance(node, list):
        return "".join(adf_to_text(n, depth) for n in node)

    kind = node.get("type")
    attrs = node.get("attrs") or {}
    kids = node.get("content")

    if kind == "text":
        text = node.get("text", "")
        for mark in node.get("marks") or []:
            mtype = mark.get("type")
            if mtype == "code":
                text = f"`{text}`"
            elif mtype == "strong":
                text = f"**{text}**"
            elif mtype == "em":
                text = f"*{text}*"
            elif mtype == "link":
                text = f"[{text}]({(mark.get('attrs') or {}).get('href', '')})"
        return text
    if kind == "hardBreak":
        return "\n"
    if kind == "mention":
        return f"@{attrs.get('text', '').lstrip('@')}"
    if kind == "emoji":
        return attrs.get("text") or attrs.get("shortName", "")
    if kind == "inlineCard":
        return attrs.get("url", "")
    if kind == "media":
        # The screenshot itself: `alt` matches the attachment filename.
        name = attrs.get("alt") or attrs.get("id", "")
        return f"[attachment: {name}]"
    if kind in ("doc", "mediaSingle", "mediaGroup", "listItem", "tableRow", "tableCell", "tableHeader"):
        return adf_to_text(kids, depth)
    if kind == "paragraph":
        return adf_to_text(kids, depth) + "\n"
    if kind == "heading":
        return f"\n{'#' * attrs.get('level', 1)} {adf_to_text(kids, depth).strip()}\n"
    if kind == "rule":
        return "\n---\n"
    if kind == "codeBlock":
        return f"\n```{attrs.get('language') or ''}\n{adf_to_text(kids, depth).rstrip()}\n```\n"
    if kind in ("blockquote", "panel"):
        body = adf_to_text(kids, depth).strip()
        return "\n" + "\n".join(f"> {line}" for line in body.splitlines()) + "\n"
    if kind in ("bulletList", "orderedList"):
        out = []
        for i, item in enumerate(kids or [], 1):
            bullet = "-" if kind == "bulletList" else f"{i}."
            body = adf_to_text(item, depth + 1).strip()
            lines = body.splitlines() or [""]
            pad = "  " * depth
            out.append(f"{pad}{bullet} {lines[0]}")
            out.extend(f"{pad}   {line}" for line in lines[1:])
        return "\n".join(out) + "\n"
    if kind == "table":
        return "\n".join(
            " | ".join(adf_to_text(cell, depth).strip() for cell in (row.get("content") or []))
            for row in (kids or [])
        ) + "\n"
    return adf_to_text(kids, depth)


# --------------------------------------------------------------- Markdown -> ADF

_BULLET = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
_INLINE = re.compile(
    r"\[(?P<ltext>[^\]]+)\]\((?P<lhref>[^)\s]+)\)"
    r"|`(?P<code>[^`]+)`"
    r"|\*\*(?P<strong>[^*]+)\*\*"
    r"|(?<!\*)\*(?P<em>[^*\s][^*]*)\*(?!\*)"
)


def _inline(text: str) -> list:
    """Markdown inline spans -> ADF text nodes. Newlines become hardBreaks."""
    out: list = []

    def plain(chunk: str) -> None:
        for i, part in enumerate(chunk.split("\n")):
            if i:
                out.append({"type": "hardBreak"})
            if part:
                out.append({"type": "text", "text": part})

    pos = 0
    for m in _INLINE.finditer(text):
        plain(text[pos : m.start()])
        if m.group("code"):
            out.append({"type": "text", "text": m.group("code"), "marks": [{"type": "code"}]})
        elif m.group("strong"):
            out.append({"type": "text", "text": m.group("strong"), "marks": [{"type": "strong"}]})
        elif m.group("em"):
            out.append({"type": "text", "text": m.group("em"), "marks": [{"type": "em"}]})
        else:
            out.append(
                {
                    "type": "text",
                    "text": m.group("ltext"),
                    "marks": [{"type": "link", "attrs": {"href": m.group("lhref")}}],
                }
            )
        pos = m.end()
    plain(text[pos:])
    return out


def _paragraph(text: str) -> dict:
    kids = _inline(text)
    return {"type": "paragraph", "content": kids} if kids else {"type": "paragraph"}


def _parse_list(lines: list[str], i: int) -> tuple[dict, int]:
    first = _BULLET.match(lines[i])
    base = len(first.group(1))
    ordered = first.group(2) not in ("-", "*", "+")
    items: list = []
    while i < len(lines):
        m = _BULLET.match(lines[i])
        if not m:
            break
        indent = len(m.group(1))
        if indent < base:
            break
        if indent > base:
            sub, i = _parse_list(lines, i)
            if items:
                items[-1]["content"].append(sub)
            continue
        if (m.group(2) not in ("-", "*", "+")) != ordered:
            break
        items.append({"type": "listItem", "content": [_paragraph(m.group(3))]})
        i += 1
    return {"type": "orderedList" if ordered else "bulletList", "content": items}, i


def md_to_adf(text: str) -> dict:
    """A pragmatic Markdown subset -> ADF: headings, fenced code, lists, quotes, rules, inline marks."""
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            node: dict = {"type": "codeBlock"}
            if lang:
                node["attrs"] = {"language": lang}
            if buf:
                node["content"] = [{"type": "text", "text": "\n".join(buf)}]
            blocks.append(node)
            continue
        if not line.strip():
            i += 1
            continue
        if _RULE.match(line):
            blocks.append({"type": "rule"})
            i += 1
            continue
        m = _HEADING.match(line)
        if m:
            blocks.append(
                {"type": "heading", "attrs": {"level": len(m.group(1))}, "content": _inline(m.group(2))}
            )
            i += 1
            continue
        if _BULLET.match(line):
            node, i = _parse_list(lines, i)
            blocks.append(node)
            continue
        if line.lstrip().startswith(">"):
            buf = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            blocks.append({"type": "blockquote", "content": [_paragraph("\n".join(buf))]})
            continue
        buf = []
        while i < len(lines) and lines[i].strip():
            nxt = lines[i]
            if buf and (
                _HEADING.match(nxt) or _BULLET.match(nxt) or _RULE.match(nxt)
                or nxt.strip().startswith(("```", ">"))
            ):
                break
            buf.append(nxt.strip())
            i += 1
        blocks.append(_paragraph("\n".join(buf)))
    return {"type": "doc", "version": 1, "content": blocks or [{"type": "paragraph"}]}


# ------------------------------------------------------------------------- commands


def _person(v) -> str:
    return (v or {}).get("displayName") or (v or {}).get("emailAddress") or "-"


def cmd_show(args) -> None:
    data = acli_json("view", args.key, "--fields", "*all")
    f = data.get("fields") or {}

    print(f"# {args.key} — {f.get('summary', '')}\n")
    print(f"- Type: {(f.get('issuetype') or {}).get('name', '-')}")
    print(f"- Status: {(f.get('status') or {}).get('name', '-')}")
    print(f"- Priority: {(f.get('priority') or {}).get('name', '-')}")
    print(f"- Reporter: {_person(f.get('reporter'))}")
    print(f"- Assignee: {_person(f.get('assignee'))}")
    print(f"- Created: {f.get('created', '-')}   Updated: {f.get('updated', '-')}")
    versions = ", ".join(v.get("name", "") for v in f.get("versions") or [])
    if versions:
        print(f"- Affects: {versions}")

    body = adf_to_text(f.get("description")).strip()
    print(f"\n## Description\n\n{body or '(empty)'}")

    files = f.get("attachment") or []
    if files:
        print("\n## Attachments\n")
        for a in files:
            print(f"- {a.get('filename')}  (id {a.get('id')}, {a.get('mimeType')}, {a.get('size')} bytes)")
        print(f"\nDownload them with: {sys.argv[0]} attachments {args.key}")

    comments = ((f.get("comment") or {}).get("comments")) or []
    print(f"\n## Comments ({len(comments)})\n")
    for c in comments:
        tag = "" if c.get("jsdPublic", True) else "  [internal]"
        print(f"### {_person(c.get('author'))} — {c.get('created', '')}{tag}\n")
        print(adf_to_text(c.get("body")).strip() + "\n")


def cmd_attachments(args) -> None:
    profile = acli_profile()
    data = acli_json("view", args.key, "--fields", "attachment")
    files = (data.get("fields") or {}).get("attachment") or []
    if not files:
        print(f"{args.key} has no attachments.")
        return

    if args.list:
        for a in files:
            print(f"{a['id']}\t{a['size']:>9}\t{a['mimeType']}\t{a['filename']}")
        return

    out_dir = Path(args.out or Path(os.environ.get("TMPDIR", "/tmp")) / f"jira-{args.key}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for a in files:
        if args.name and args.name.lower() not in a["filename"].lower():
            continue
        # Route through the site host: the `content` URL points at an internal Atlassian host.
        url = f"https://{profile['site']}/rest/api/3/attachment/content/{a['id']}"
        target = out_dir / re.sub(r"[/\\]", "_", a["filename"])
        target.write_bytes(rest(url, profile))
        print(f"{target}  ({a['mimeType']}, {target.stat().st_size} bytes)")


def cmd_comment(args) -> None:
    if args.file:
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    else:
        text = args.body
    text = text.strip()
    if not text:
        sys.exit("Refusing to post an empty comment.")

    internal = not args.public
    if args.public and not args.yes:
        sys.exit(
            "--public posts a reply the customer who reported the ticket will see.\n"
            "Re-run with --yes if that is really what you want."
        )

    adf = md_to_adf(text)
    if args.dry_run:
        print(f"[dry run] {'INTERNAL note' if internal else 'PUBLIC reply'} on {args.key}\n")
        print(json.dumps(adf, indent=2, ensure_ascii=False))
        print("\n--- renders back as ---\n")
        print(adf_to_text(adf).strip())
        return

    profile = acli_profile()
    url = f"https://{profile['site']}/rest/api/3/issue/{args.key}/comment"
    payload = {
        "body": adf,
        # The only way to set JSM internal/public; `acli` cannot reach this property.
        "properties": [{"key": "sd.public.comment", "value": {"internal": internal}}],
    }
    created = json.loads(rest(url, profile, payload))
    kind = "internal note" if not created.get("jsdPublic", not internal) else "PUBLIC reply"
    print(f"Posted {kind} {created.get('id')} on {args.key}")
    print(f"https://{profile['site']}/browse/{args.key}?focusedCommentId={created.get('id')}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    show = sub.add_parser("show", help="render an issue (description + comments) as Markdown")
    show.add_argument("key")
    show.set_defaults(func=cmd_show)

    att = sub.add_parser("attachments", help="list or download the files attached to an issue")
    att.add_argument("key")
    att.add_argument("--list", action="store_true", help="list only, do not download")
    att.add_argument("--out", help="target directory (default: a temp dir named after the issue)")
    att.add_argument("--name", help="only download attachments whose filename contains this")
    att.set_defaults(func=cmd_attachments)

    com = sub.add_parser("comment", help="post a comment, internal by default (Markdown -> ADF)")
    com.add_argument("key")
    src = com.add_mutually_exclusive_group(required=True)
    src.add_argument("-F", "--file", help="Markdown file to post, or '-' for stdin")
    src.add_argument("-b", "--body", help="Markdown text to post")
    com.add_argument("--public", action="store_true", help="post as a reply the reporter can see")
    com.add_argument("--yes", action="store_true", help="required confirmation for --public")
    com.add_argument("--dry-run", action="store_true", help="print the ADF and exit without posting")
    com.set_defaults(func=cmd_comment)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
