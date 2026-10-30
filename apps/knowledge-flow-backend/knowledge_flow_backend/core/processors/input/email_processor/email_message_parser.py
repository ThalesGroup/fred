# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared `.msg` / `.eml` parsing for the library and chat attachment processors.

Headers, the body and attachment names are read, plus attached mails (parsed the
same way) and the text of document attachments (fast text processors, deduplicated
by SHA-256); Bcc and remote resources never are. Full rationale: openspec spec email-ingestion.
"""

from __future__ import annotations

import email
import email.utils
import hashlib
import logging
import re
import tempfile
import threading
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import EmailMessage, Message, MIMEPart
from functools import partial
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify
from oxmsg import Message as OutlookMessage
from oxmsg.attachment import Attachment as OutlookAttachment
from oxmsg.properties import Properties as OutlookProperties
from oxmsg.storage import Storage as OutlookStorage
from oxmsg.util import lazyproperty

from knowledge_flow_backend.core.processors.input.common.base_input_processor import InputValidationError
from knowledge_flow_backend.core.processors.input.common.legacy_office import looks_like_ole_binary
from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import BaseFastTextProcessor, FastTextOptions
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_doc_processor import FastLiteDocProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_docx_processor import FastLiteDocxProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_odt_processor import FastLiteOdtProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pdf_processor import FastLitePdfProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_ppt_processor import FastLitePptProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pptx_processor import FastLitePptxProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_plain_text_processor import FastPlainTextProcessor

logger = logging.getLogger(__name__)

EMAIL_SUFFIXES = (".msg", ".eml")
MAX_EMAIL_FILE_BYTES = 25 * 1024 * 1024
LIBRARY_MAX_BODY_CHARS = 1_000_000
BODY_NOT_EXTRACTABLE = "_The message body could not be extracted (no plain-text or HTML version)._"
ATTACHED_MESSAGE_UNREADABLE = "_This attached message could not be read (encrypted or damaged)._"
MAX_ATTACHED_MESSAGES = 20
MAX_ATTACHED_DEPTH = 3
ATTACHMENT_NOT_EXTRACTABLE = "_Attachment text could not be extracted._"
MAX_EXTRACTED_ATTACHMENTS = 10
MAX_ATTACHMENT_CHARS = 100_000
MAX_ATTACHMENT_EXTRACT_BYTES = 15 * 1024 * 1024
ATTACHMENT_TIMEOUT_SECONDS = 60.0
# The chat attachment fast processors; archives, images and executables stay names-only.
_TEXT_PROCESSORS: dict[str, type[BaseFastTextProcessor]] = {
    ".pdf": FastLitePdfProcessor,
    ".docx": FastLiteDocxProcessor,
    ".doc": FastLiteDocProcessor,
    ".odt": FastLiteOdtProcessor,
    ".pptx": FastLitePptxProcessor,
    ".ppt": FastLitePptProcessor,
    ".txt": FastPlainTextProcessor,
    ".md": FastPlainTextProcessor,
}
_HEADING = re.compile(r"^(#{1,6})(?=\s)", re.MULTILINE)

_REMOVED_HTML_TAGS = ("script", "style", "iframe", "object", "embed", "form", "head", "link", "meta", "noscript", "svg", "applet", "base")
_SAFE_LINK_SCHEMES = ("http://", "https://", "mailto:")
_SIGNATURE_TYPES = {"application/pkcs7-signature", "application/x-pkcs7-signature", "application/pgp-signature"}
_ENCRYPTED_TYPES = {"application/pkcs7-mime", "application/x-pkcs7-mime", "multipart/encrypted"}

# MAPI property ids not exposed by python-oxmsg's own accessors.
_PID_RECIPIENT_TYPE = 0x0C15
_PID_SMTP_ADDRESS = 0x39FE
_PID_SENDER_NAME = 0x0C1A
_PID_SENDER_SMTP_ADDRESS = 0x5D01
_PID_SENDER_EMAIL_ADDRESS = 0x0C1F
_PID_INTERNET_MESSAGE_ID = 0x1035
_PID_IN_REPLY_TO_ID = 0x1042
_PID_ATTACH_METHOD = 0x3705
_PID_DISPLAY_NAME = 0x3001
_MAPI_TO, _MAPI_CC = 1, 2
_ATTACH_EMBEDDED_MSG = 5
_EMBEDDED_MSG_STORAGE = "__substg1.0_3701000D"
_EMBEDDED_MSG_HDR_OFFSET = 24  # [MS-OXMSG] 2.4.1.2: an embedded message's header lacks the top-level 8 reserved bytes


class EncryptedEmailError(InputValidationError):
    """An encrypted or rights-protected message: retrying cannot help."""


@dataclass(frozen=True)
class EmailAttachment:
    name: str
    size_bytes: int
    # Kept only for document types small enough to extract.
    content: bytes | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ParsedEmail:
    subject: str | None = None
    sender: str | None = None
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    sent_at: datetime | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    body_markdown: str | None = None
    attachments: list[EmailAttachment] = field(default_factory=list)
    attached_messages: list[AttachedMessage] = field(default_factory=list)
    encrypted: bool = False


@dataclass(frozen=True)
class AttachedMessage:
    """A mail attached to a mail; `parsed` is None when it could not be read."""

    name: str
    parsed: ParsedEmail | None


@dataclass
class _AttachedBudget:
    remaining: int = MAX_ATTACHED_MESSAGES


def parse_email_file(file_path: Path) -> ParsedEmail:
    """Parse one `.msg` or `.eml` file, refusing oversized files before reading them."""
    size = file_path.stat().st_size
    if size > MAX_EMAIL_FILE_BYTES:
        raise InputValidationError(f"The mail file is {size / (1024 * 1024):.1f} MB; the limit is {MAX_EMAIL_FILE_BYTES // (1024 * 1024)} MB. Remove large attachments and export it again.")
    suffix = file_path.suffix.lower()
    if suffix == ".msg":
        return _parse_msg(file_path)
    if suffix == ".eml":
        return _parse_eml(file_path.read_bytes(), 0, _AttachedBudget())
    raise ValueError(f"Unsupported mail file suffix '{suffix}'")


def render_email_markdown(parsed: ParsedEmail, *, max_body_chars: int | None = None) -> str:
    """Header block, body, attachment names and texts, then each attached mail. Raises for encrypted messages.

    `max_body_chars` is shared by every body and attachment text of the file, in rendering order.
    """
    if parsed.encrypted:
        raise EncryptedEmailError("This mail is encrypted or rights-protected (S/MIME or IRM), so its content cannot be read. Send an unencrypted copy instead.")
    budget, texts = _BodyBudget(max_body_chars), _AttachmentTexts()
    parts = _render_message(parsed, budget, texts, 2) + _render_attached(parsed.attached_messages, "", budget, texts)
    return "\n\n".join(p for p in parts if p) + "\n"


class _BodyBudget:
    def __init__(self, limit: int | None):
        self.limit, self.remaining = limit, limit

    @property
    def exhausted(self) -> bool:
        return self.remaining is not None and self.remaining <= 0

    def take(self, body: str) -> str:
        if self.limit is None or self.remaining is None:
            return body
        if len(body) <= self.remaining:
            self.remaining -= len(body)
            return body
        kept, self.remaining = body[: self.remaining].rstrip(), 0
        marker = f"_[Body truncated: the message exceeds {self.limit:,} characters.]_"
        return f"{kept}\n\n{marker}" if kept else marker


class _AttachmentTexts:
    """Extracts each distinct attachment content once per file, within the caps."""

    def __init__(self) -> None:
        self.first_name_by_digest: dict[str, str] = {}
        self.extracted = 0
        self.timed_out = False

    def sections(self, attachments: list[EmailAttachment], level: int, budget: _BodyBudget) -> list[str]:
        parts: list[str] = []
        for attachment in attachments:
            if attachment.content is None:
                continue
            digest = hashlib.sha256(attachment.content).hexdigest()
            heading = f"{'#' * level} Attachment: {attachment.name} ({_format_size(attachment.size_bytes)})"
            if (first := self.first_name_by_digest.get(digest)) is not None:
                parts += [heading, f"_Same file as {first} above._"]
                continue
            # After a timeout the stuck extraction still runs, so no other one starts.
            if self.extracted >= MAX_EXTRACTED_ATTACHMENTS or budget.exhausted or self.timed_out:
                continue
            self.extracted += 1
            self.first_name_by_digest[digest] = attachment.name
            text = self._extract(attachment)
            parts += [heading, budget.take(_HEADING.sub(lambda m: "#" * min(6, len(m.group(1)) + level), text)) if text else ATTACHMENT_NOT_EXTRACTABLE]
        return parts

    def _extract(self, attachment: EmailAttachment) -> str | None:
        suffix = Path(attachment.name).suffix.lower()
        outcome: dict[str, str] = {}
        with tempfile.TemporaryDirectory(prefix="mail_attachment_") as tmp:
            path = Path(tmp) / f"attachment{suffix}"
            path.write_bytes(attachment.content or b"")
            # A daemon thread bounds the wait; LibreOffice conversions carry their own timeout.
            worker = threading.Thread(target=_extract_text, args=(attachment.name, path, outcome), daemon=True, name="mail-attachment-text")
            worker.start()
            worker.join(ATTACHMENT_TIMEOUT_SECONDS)
            if worker.is_alive():
                logger.warning("[EMAIL] attachment %r: text extraction exceeded %ss", attachment.name, ATTACHMENT_TIMEOUT_SECONDS)
                self.timed_out = True
                return None
        return outcome.get("text") or None


_PROCESSOR_INSTANCES: dict[type[BaseFastTextProcessor], BaseFastTextProcessor] = {}


def _extract_text(name: str, path: Path, outcome: dict[str, str]) -> None:
    try:
        if not _has_expected_signature(path):
            raise ValueError("content does not match its extension (encrypted Office files are OLE containers)")
        cls = _TEXT_PROCESSORS[path.suffix]
        processor = _PROCESSOR_INSTANCES.setdefault(cls, cls())
        # Slide headings let a question name a slide; PDF page markers stay off.
        options = FastTextOptions(max_chars=MAX_ATTACHMENT_CHARS, add_page_headings=path.suffix in (".pptx", ".ppt"))
        outcome["text"] = processor.extract(path, options).text.strip()
    except Exception as exc:  # noqa: BLE001 - encrypted or damaged attachments must never fail the mail
        logger.info("[EMAIL] attachment %r: text could not be extracted: %s", name, exc)


def _has_expected_signature(path: Path) -> bool:
    # The lite readers fall back to reading unknown bytes as text, which would index binary noise.
    if path.suffix in (".docx", ".pptx", ".odt"):
        return zipfile.is_zipfile(path)
    if path.suffix in (".doc", ".ppt"):
        return looks_like_ole_binary(path)
    if path.suffix == ".pdf":
        with path.open("rb") as handle:
            return b"%PDF-" in handle.read(1024)
    return True


def _text_attachment(name: str, size_bytes: int, read: Callable[[], object]) -> EmailAttachment:
    """List an attachment, keeping its bytes when it is a document type within the size cap."""
    content = None
    if Path(name).suffix.lower() in _TEXT_PROCESSORS and 0 < size_bytes <= MAX_ATTACHMENT_EXTRACT_BYTES:
        raw = read()
        content = raw if isinstance(raw, bytes) and raw else None
    return EmailAttachment(name=name, size_bytes=size_bytes, content=content)


def _render_message(parsed: ParsedEmail, budget: _BodyBudget, texts: _AttachmentTexts, level: int) -> list[str]:
    header_lines = [
        ("From", parsed.sender),
        ("To", ", ".join(parsed.to)),
        ("Cc", ", ".join(parsed.cc)),
        ("Date", parsed.sent_at.isoformat(sep=" ") if parsed.sent_at else None),
        ("Subject", parsed.subject),
    ]
    parts = ["\n".join(f"- **{label}:** {value}" for label, value in header_lines if value), "---"]
    body = (parsed.body_markdown or "").strip()
    parts.append(budget.take(body) if body else BODY_NOT_EXTRACTABLE)
    if parsed.attachments:
        listing = "\n".join(f"- {a.name} ({_format_size(a.size_bytes)})" for a in parsed.attachments)
        parts.append(f"{'#' * level} Attachments\n\n{listing}")
        parts += texts.sections(parsed.attachments, level + 1, budget)
    return parts


def _render_attached(messages: list[AttachedMessage], prefix: str, budget: _BodyBudget, texts: _AttachmentTexts) -> list[str]:
    parts: list[str] = []
    for index, attached in enumerate(messages, start=1):
        number, inner = f"{prefix}{index}", attached.parsed
        parts.append(f"## Attached message {number}: {(inner.subject if inner else None) or attached.name}")
        if inner is None or inner.encrypted:
            parts.append(ATTACHED_MESSAGE_UNREADABLE)
            continue
        parts += _render_message(inner, budget, texts, 3)
        parts += _render_attached(inner.attached_messages, f"{number}.", budget, texts)
    return parts


def email_metadata(parsed: ParsedEmail) -> dict:
    """Flat enrichment dict for `BaseInputProcessor._apply_enrichment`."""
    return {"title": parsed.subject, "author": parsed.sender, "created": parsed.sent_at}


def email_extension(parsed: ParsedEmail) -> dict:
    """`extensions.email` payload; Bcc is deliberately absent."""
    return {"to": parsed.to, "cc": parsed.cc, "message_id": parsed.message_id, "in_reply_to": parsed.in_reply_to}


def html_to_markdown(html: str) -> str:
    """Strip active and remote content, then convert. Images keep only their alt text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_REMOVED_HTML_TAGS):
        tag.decompose()
    for img in soup.find_all("img"):
        alt = str(img.get("alt") or "").strip()
        img.replace_with(alt)
    for tag in soup.find_all(True):
        for attr in [a for a in tag.attrs if a.lower().startswith("on") or a.lower() in ("style", "background", "srcset")]:
            del tag.attrs[attr]
        href = tag.get("href")
        if href is not None and not str(href).strip().lower().startswith(_SAFE_LINK_SCHEMES):
            del tag.attrs["href"]
    return markdownify(str(soup), heading_style="ATX").strip()


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_address(name: str | None, address: str | None) -> str | None:
    name, address = (name or "").strip().strip('"'), (address or "").strip()
    if name and address and name.lower() != address.lower():
        return f"{name} <{address}>"
    return address or name or None


def _addresses(header_value: str | None) -> list[str]:
    if not header_value:
        return []
    return [a for a in (_format_address(n, addr) for n, addr in email.utils.getaddresses([str(header_value)])) if a]


def _clean(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _attached_message(name: str, depth: int, budget: _AttachedBudget, parse: Callable[[], ParsedEmail]) -> AttachedMessage | None:
    """Parse one attached mail within the depth and count limits; beyond them it stays a listed name."""
    if depth > MAX_ATTACHED_DEPTH or budget.remaining <= 0:
        return None
    budget.remaining -= 1
    try:
        return AttachedMessage(name=name, parsed=parse())
    except Exception as exc:  # noqa: BLE001 - a damaged attached mail must never fail its parent
        logger.info("[EMAIL] attached message %r could not be read: %s", name, exc)
        return AttachedMessage(name=name, parsed=None)


# --- .eml -------------------------------------------------------------------------


def _parse_eml(raw: bytes, depth: int, budget: _AttachedBudget) -> ParsedEmail:
    return _parse_eml_message(email.message_from_bytes(raw, policy=policy.default), depth, budget)


def _parse_eml_message(msg: Message, depth: int, budget: _AttachedBudget) -> ParsedEmail:
    if not isinstance(msg, EmailMessage) or not msg.keys():
        raise ValueError("The file is not a readable mail message (no headers found).")
    sender = _addresses(msg.get("From"))
    encrypted = msg.get_content_type() in _ENCRYPTED_TYPES
    body_markdown, attachments, attached = (None, [], []) if encrypted else _eml_body_and_attachments(msg, depth, budget)
    return ParsedEmail(
        subject=_clean(msg.get("Subject")),
        sender=sender[0] if sender else None,
        to=_addresses(msg.get("To")),
        cc=_addresses(msg.get("Cc")),
        sent_at=_eml_date(msg),
        message_id=_clean(msg.get("Message-ID")),
        in_reply_to=_clean(msg.get("In-Reply-To")),
        body_markdown=body_markdown,
        attachments=attachments,
        attached_messages=attached,
        encrypted=encrypted,
    )


def _eml_date(msg: Message) -> datetime | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return email.utils.parsedate_to_datetime(str(raw))
    except (TypeError, ValueError):
        return None


def _eml_body_and_attachments(msg: MIMEPart, depth: int, budget: _AttachedBudget) -> tuple[str | None, list[EmailAttachment], list[AttachedMessage]]:
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body: str | None = None
    if isinstance(body_part, MIMEPart):
        content = _part_text(body_part)
        body = html_to_markdown(content) if body_part.get_content_subtype() == "html" else content
    attachments: list[EmailAttachment] = []
    attached: list[AttachedMessage] = []
    for part in _leaf_parts(msg):
        if part is body_part or part.get_content_type() in _SIGNATURE_TYPES:
            continue
        name = part.get_filename()
        if name or part.get_content_disposition() == "attachment" or part.get_content_type() == "message/rfc822":
            attachments.append(_text_attachment(name or "unnamed attachment", _part_size(part), partial(part.get_payload, decode=True)))
            parse = _eml_part_mail_parser(part, depth + 1, budget)
            if parse is not None and (message := _attached_message(name or "attached message", depth + 1, budget, parse)):
                attached.append(message)
    return body, attachments, attached


def _eml_part_mail_parser(part: MIMEPart, depth: int, budget: _AttachedBudget) -> Callable[[], ParsedEmail] | None:
    """How to parse `part` if it is a mail (message/rfc822, attached .eml or .msg), else None."""
    name = (part.get_filename() or "").lower()
    if part.get_content_type() == "message/rfc822":
        return partial(_parse_rfc822_part, part, depth, budget)
    if name.endswith((".eml", ".msg")) or part.get_content_type() == "application/vnd.ms-outlook":
        payload = part.get_payload(decode=True)
        raw = payload if isinstance(payload, bytes) else b""
        return partial(_parse_eml if name.endswith(".eml") else _parse_outlook_bytes, raw, depth, budget)
    return None


def _parse_rfc822_part(part: MIMEPart, depth: int, budget: _AttachedBudget) -> ParsedEmail:
    inner = part.get_payload(0)
    if not isinstance(inner, Message):
        raise ValueError("The message/rfc822 part holds no message.")
    return _parse_eml_message(inner, depth, budget)


def _leaf_parts(part: MIMEPart) -> Iterator[MIMEPart]:
    # A forwarded message/rfc822 is one attachment: its own parts are not listed.
    if part.get_content_type() == "message/rfc822" or not part.is_multipart():
        yield part
        return
    for sub in part.iter_parts():
        yield from _leaf_parts(sub)


def _part_size(part: MIMEPart) -> int:
    if part.get_content_type() == "message/rfc822":
        inner = part.get_payload(0)
        return len(inner.as_bytes()) if isinstance(inner, Message) else 0
    payload = part.get_payload(decode=True)
    return len(payload) if isinstance(payload, bytes) else 0


def _part_text(part: MIMEPart) -> str:
    try:
        return str(part.get_content())
    except (LookupError, UnicodeDecodeError):
        # Unknown or wrong declared charset: keep the readable bytes.
        payload = part.get_payload(decode=True)
        return payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else ""


# --- .msg -------------------------------------------------------------------------


class _EmbeddedOutlookMessage(OutlookMessage):
    """A mail stored inside a `.msg` attachment storage rather than as a file."""

    @lazyproperty
    def _properties(self) -> OutlookProperties:
        return OutlookProperties(self._storage, properties_header_offset=_EMBEDDED_MSG_HDR_OFFSET)


def _parse_msg(file_path: Path) -> ParsedEmail:
    try:
        msg = OutlookMessage.load(str(file_path))
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - olefile raises assorted types on corrupt input
        raise ValueError(f"The file is not a readable Outlook message: {exc}") from exc
    return _parse_outlook(msg, 0, _AttachedBudget())


def _parse_outlook(msg: OutlookMessage, depth: int, budget: _AttachedBudget) -> ParsedEmail:
    props = msg.properties
    headers = {name.lower(): value for name, value in msg.message_headers.items()}
    message_class = msg.message_class.upper()
    attachments = msg.attachments
    signed = "MULTIPARTSIGNED" in message_class
    encrypted = (message_class.startswith("IPM.NOTE.SMIME") and not signed) or ".RPMSG" in message_class or any((a.file_name or "").lower() == "message.rpmsg" for a in attachments)

    to, cc = [], []
    for recipient in msg.recipients:
        kind = recipient.properties.int_prop_value(_PID_RECIPIENT_TYPE)
        address = _format_address(recipient.name, recipient.properties.str_prop_value(_PID_SMTP_ADDRESS) or recipient.email_address)
        if address and kind == _MAPI_TO:
            to.append(address)
        elif address and kind == _MAPI_CC:
            cc.append(address)
    if not to and not cc:
        to, cc = _addresses(headers.get("to")), _addresses(headers.get("cc"))

    sender_from_header = _addresses(headers.get("from"))
    sender = (
        sender_from_header[0]
        if sender_from_header
        else _format_address(props.str_prop_value(_PID_SENDER_NAME), props.str_prop_value(_PID_SENDER_SMTP_ADDRESS) or props.str_prop_value(_PID_SENDER_EMAIL_ADDRESS))
    )

    body_markdown: str | None = None
    listed: list[EmailAttachment] = []
    attached: list[AttachedMessage] = []
    if not encrypted:
        body_markdown = _clean(msg.body)
        if body_markdown is None and (html := msg.html_body):
            body_markdown = html_to_markdown(html) or None
        signed_mime: EmailMessage | None = None
        if signed and body_markdown is None:
            # Outlook keeps a signed message's MIME (body and files) in one smime.p7m attachment.
            inner = next((a for a in attachments if a.file_bytes and (a.file_name or "").lower().endswith(".p7m")), None)
            if inner is not None and inner.file_bytes:
                inner_msg = email.message_from_bytes(inner.file_bytes, policy=policy.default)
                signed_mime = inner_msg if isinstance(inner_msg, EmailMessage) else None
        if signed_mime is not None:
            body_markdown, listed, attached = _eml_body_and_attachments(signed_mime, depth, budget)
        else:
            listed, attached = _msg_attachments(attachments, depth + 1, budget)

    return ParsedEmail(
        subject=_clean(msg.subject),
        sender=sender,
        to=to,
        cc=cc,
        sent_at=msg.sent_date,
        message_id=_clean(props.str_prop_value(_PID_INTERNET_MESSAGE_ID) or headers.get("message-id")),
        in_reply_to=_clean(props.str_prop_value(_PID_IN_REPLY_TO_ID) or headers.get("in-reply-to")),
        body_markdown=body_markdown,
        attachments=listed,
        attached_messages=attached,
        encrypted=encrypted,
    )


def _msg_attachments(attachments: tuple[OutlookAttachment, ...], depth: int, budget: _AttachedBudget) -> tuple[list[EmailAttachment], list[AttachedMessage]]:
    listed: list[EmailAttachment] = []
    attached: list[AttachedMessage] = []
    for a in attachments:
        parse: Callable[[], ParsedEmail] | None = None
        file_name = a.file_name or ""
        if a.properties.int_prop_value(_PID_ATTACH_METHOD) == _ATTACH_EMBEDDED_MSG:
            parent = a._storage
            storage = next((s for s in parent.storages if s.name == _EMBEDDED_MSG_STORAGE), None) if isinstance(parent, OutlookStorage) else None
            name = file_name or a.properties.str_prop_value(_PID_DISPLAY_NAME) or "attached message"
            listed.append(EmailAttachment(name=name, size_bytes=_storage_size(storage) if storage else 0))
            parse = partial(_parse_embedded_outlook, storage, depth, budget)
        else:
            name = file_name or "unnamed attachment"
            listed.append(_text_attachment(name, a.size, lambda a=a: a.file_bytes))
            if file_name.lower().endswith(".msg"):
                parse = partial(_parse_outlook_bytes, a.file_bytes or b"", depth, budget)
            elif file_name.lower().endswith(".eml"):
                parse = partial(_parse_eml, a.file_bytes or b"", depth, budget)
        if parse is not None and (message := _attached_message(name, depth, budget, parse)):
            attached.append(message)
    return listed, attached


def _parse_embedded_outlook(storage: OutlookStorage | None, depth: int, budget: _AttachedBudget) -> ParsedEmail:
    if storage is None:
        raise ValueError("The embedded message storage is missing.")
    return _parse_outlook(_EmbeddedOutlookMessage(storage), depth, budget)


def _parse_outlook_bytes(raw: bytes, depth: int, budget: _AttachedBudget) -> ParsedEmail:
    return _parse_outlook(OutlookMessage.load(raw), depth, budget)


def _storage_size(storage: OutlookStorage) -> int:
    return sum(len(s.bytes_) for s in storage.streams) + sum(_storage_size(sub) for sub in storage.storages)
