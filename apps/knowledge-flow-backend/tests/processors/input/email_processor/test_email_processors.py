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

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import pytest

from knowledge_flow_backend.core.processors.input.common.base_input_processor import InputValidationError
from knowledge_flow_backend.core.processors.input.email_processor import email_message_parser
from knowledge_flow_backend.core.processors.input.email_processor.email_markdown_processor import EmailMarkdownProcessor
from knowledge_flow_backend.core.processors.input.email_processor.email_message_parser import ATTACHED_MESSAGE_UNREADABLE, BODY_NOT_EXTRACTABLE, EncryptedEmailError
from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import FastTextOptions
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_email_processor import FastEmailProcessor
from knowledge_flow_backend.core.processors.output.vectorization_processor.vectorization_utils import flat_metadata_from
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController
from knowledge_flow_backend.features.scheduler.extraction_process import _is_permanent

FIXTURES = Path(__file__).parent / "fixtures"


def _library_markdown(file_path: Path, output_dir: Path) -> str:
    result = EmailMarkdownProcessor().convert_file_to_markdown(file_path, output_dir, None)
    return Path(result["md_file"]).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("fixture", "title", "author", "created", "to", "cc", "body", "attachments"),
    [
        (
            "plain_with_attachments.eml",
            "Réunion budget 2027",
            "José García <jose.garcia@example.com>",
            datetime(2026, 10, 27, 10, 30, tzinfo=timezone(timedelta(hours=1))),
            ["Bob Martin <bob@example.com>", "alice@example.com"],
            ["Carol White <carol@example.com>"],
            "Le budget est en pièce jointe.",
            ["budget.pdf", "chart.png"],
        ),
        (
            "plain_with_attachments.msg",
            "Budget review 2027",
            "Jane Doe <jane.doe@example.com>",
            datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc),
            ["Bob Martin <bob@example.com>"],
            ["Carol White <carol@example.com>"],
            "Please review the budget before Friday.",
            ["report.pdf", "photo.png"],
        ),
    ],
)
def test_headers_body_metadata_and_attachment_names(tmp_path, fixture, title, author, created, to, cc, body, attachments):
    file_path = FIXTURES / fixture
    processor = EmailMarkdownProcessor()
    assert processor.check_file_validity(file_path)

    metadata = processor.process_metadata(file_path, [], "uploads")
    assert metadata.identity.title == title
    assert metadata.identity.author == author
    assert metadata.identity.created == created
    assert metadata.extensions is not None
    email_ext = metadata.extensions["email"]
    assert email_ext["to"] == to
    assert email_ext["cc"] == cc
    assert email_ext["message_id"] and email_ext["in_reply_to"]
    assert "bcc" not in email_ext
    assert flat_metadata_from(metadata)["author"] == author

    markdown = _library_markdown(file_path, tmp_path / "out")
    assert f"- **From:** {author}" in markdown
    assert f"- **Subject:** {title}" in markdown
    assert f"- **Cc:** {cc[0]}" in markdown
    assert body in markdown
    assert "## Attachments" in markdown
    for name in attachments:
        assert f"- {name} (" in markdown
    # Bcc and attachment bytes never reach the markdown.
    assert "hidden@example.com" not in markdown and "Hidden Person" not in markdown
    assert "SECRET" not in markdown


@pytest.mark.parametrize("fixture", ["html_hostile.eml", "html_only.msg"])
def test_html_body_is_sanitised(tmp_path, fixture):
    markdown = _library_markdown(FIXTURES / fixture, tmp_path / "out")

    assert "Quarterly **numbers** attached." in markdown
    assert "[report](https://example.com/report)" in markdown
    assert "Company logo" in markdown
    for forbidden in ("alert", "<script", "color:red", "onclick", "steal()", "tracker.example.com", "evil.example.com", "javascript:", "<img", "<iframe"):
        assert forbidden not in markdown


def test_plain_text_is_preferred_over_html(tmp_path):
    markdown = _library_markdown(FIXTURES / "alternative.eml", tmp_path / "out")

    assert "Plain version wins." in markdown
    assert "HTML version loses." not in markdown


def test_missing_subject_falls_back_to_file_stem(tmp_path):
    file_path = FIXTURES / "no_subject.eml"
    metadata = EmailMarkdownProcessor().process_metadata(file_path, [], "uploads")

    assert metadata.identity.title == "no_subject"
    assert metadata.identity.created is None
    markdown = _library_markdown(file_path, tmp_path / "out")
    assert "**Subject:**" not in markdown and "**Cc:**" not in markdown
    assert "No subject, no Cc, broken date." in markdown


def test_rtf_only_body_keeps_header_and_attachments(tmp_path):
    markdown = _library_markdown(FIXTURES / "rtf_only.msg", tmp_path / "out")

    assert "- **Subject:** RTF only" in markdown
    assert BODY_NOT_EXTRACTABLE in markdown
    assert "- notes.docx (" in markdown


@pytest.mark.parametrize(("fixture", "body", "attachment"), [("signed.eml", "This message is signed but readable.", None), ("signed.msg", "Signed body text.", "contract.pdf")])
def test_signed_only_messages_are_ingested(tmp_path, fixture, body, attachment):
    markdown = _library_markdown(FIXTURES / fixture, tmp_path / "out")

    assert body in markdown
    assert "smime.p7s" not in markdown
    if attachment:
        assert f"- {attachment} (" in markdown


@pytest.mark.parametrize("fixture", ["encrypted.eml", "encrypted.msg"])
def test_encrypted_messages_fail_permanently_on_both_paths(tmp_path, fixture):
    file_path = FIXTURES / fixture
    # Headers stay readable, so the upload's metadata step succeeds.
    assert EmailMarkdownProcessor().process_metadata(file_path, [], "uploads").identity.author

    with pytest.raises(EncryptedEmailError, match="encrypted") as library_error:
        EmailMarkdownProcessor().convert_file_to_markdown(file_path, tmp_path / "out", None)
    assert isinstance(library_error.value, ValueError)
    assert _is_permanent(library_error.value)

    with pytest.raises(EncryptedEmailError):
        FastEmailProcessor().extract(file_path)


def test_oversized_file_is_rejected_before_parsing(tmp_path, monkeypatch):
    file_path = tmp_path / "huge.eml"
    with file_path.open("wb") as handle:
        handle.truncate(email_message_parser.MAX_EMAIL_FILE_BYTES + 1)  # sparse: no real 25 MB write

    def _must_not_parse(_raw: bytes):
        raise AssertionError("parsed an oversized file")

    monkeypatch.setattr(email_message_parser, "_parse_eml", _must_not_parse)
    with pytest.raises(InputValidationError, match="limit is 25 MB"):
        EmailMarkdownProcessor().convert_file_to_markdown(file_path, tmp_path / "out", None)
    with pytest.raises(InputValidationError, match="limit is 25 MB"):
        FastEmailProcessor().extract(file_path)


def test_library_body_is_truncated_with_a_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.email_processor.email_markdown_processor.LIBRARY_MAX_BODY_CHARS",
        100,
    )
    file_path = tmp_path / "long.eml"
    file_path.write_text("From: a@example.com\nSubject: Long\nContent-Type: text/plain\n\n" + "word " * 200, encoding="utf-8")

    markdown = _library_markdown(file_path, tmp_path / "out")

    assert "_[Body truncated: the message exceeds 100 characters.]_" in markdown
    assert markdown.count("word") < 30


def test_malformed_msg_is_a_permanent_error(tmp_path):
    file_path = tmp_path / "broken.msg"
    file_path.write_bytes(b"this is not an OLE file")

    with pytest.raises(ValueError) as error:
        EmailMarkdownProcessor().convert_file_to_markdown(file_path, tmp_path / "out", None)
    assert _is_permanent(error.value)


@pytest.mark.parametrize("fixture", ["plain_with_attachments.eml", "plain_with_attachments.msg"])
def test_attachment_path_uses_the_same_layout_within_the_fast_text_cap(tmp_path, fixture):
    file_path = FIXTURES / fixture
    library = _library_markdown(file_path, tmp_path / "out")

    result = FastEmailProcessor().extract(file_path)
    assert result.text.strip() == library.strip()
    assert result.truncated is False
    assert result.extras["file_type"] == "email"

    capped = FastEmailProcessor().extract(file_path, FastTextOptions(max_chars=80))
    assert capped.truncated is True
    assert len(capped.text) <= 82


def test_default_attachment_registry_routes_mail_suffixes():
    controller = object.__new__(IngestionController)

    registry = controller._build_fast_text_registry()

    assert registry[".msg"] is FastEmailProcessor
    assert registry[".eml"] is FastEmailProcessor


def _mail(subject: str, body: str, attached: list[EmailMessage] = ()) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "a@example.com", "b@example.com", subject
    msg.set_content(body)
    for inner in attached:
        msg.add_attachment(inner)  # message/rfc822 part
    return msg


def _write(tmp_path: Path, msg: EmailMessage) -> Path:
    file_path = tmp_path / "generated.eml"
    file_path.write_bytes(msg.as_bytes())
    return file_path


@pytest.mark.parametrize(
    ("fixture", "parent_title", "attached_headings", "attached_bodies", "inner_attachment"),
    [
        ("forwarded.eml", "Fwd: quarterly figures", ["## Attached message 1: Quarterly figures"], ["The figures for Q3 are attached."], "q3.xls"),
        (
            "with_embedded.msg",
            "Fwd: supplier contract",
            ["## Attached message 1: Supplier contract draft", "## Attached message 2: Meeting minutes"],
            ["Here is the draft contract for review.", "Minutes of the weekly meeting."],
            "contract.pdf",
        ),
    ],
)
def test_attached_messages_are_appended_after_the_parent(tmp_path, fixture, parent_title, attached_headings, attached_bodies, inner_attachment):
    file_path = FIXTURES / fixture
    markdown = _library_markdown(file_path, tmp_path / "out")

    for heading, body in zip(attached_headings, attached_bodies, strict=True):
        assert heading in markdown and body in markdown
        assert markdown.index(heading) > markdown.index("## Attachments")
    assert "- **From:** Alan Smith <alan@example.com>" in markdown
    assert f"### Attachments\n\n- {inner_attachment} (" in markdown
    assert "hidden@example.com" not in markdown and "SECRET" not in markdown
    # Metadata stays the parent's.
    metadata = EmailMarkdownProcessor().process_metadata(file_path, [], "uploads")
    assert metadata.identity.title == parent_title
    assert metadata.identity.author == "Jane Doe <jane.doe@example.com>"
    assert metadata.extensions is not None and metadata.extensions["email"]["to"] == ["Bob Martin <bob@example.com>"]
    # The attachment path renders the same text.
    assert FastEmailProcessor().extract(file_path).text.strip() == markdown.strip()


@pytest.mark.parametrize("fixture", ["encrypted_attached.eml", "with_unreadable_attached.msg"])
def test_unreadable_attached_message_gets_a_note_and_never_fails_the_parent(tmp_path, fixture):
    markdown = _library_markdown(FIXTURES / fixture, tmp_path / "out")

    assert "## Attached message 1: " in markdown
    assert ATTACHED_MESSAGE_UNREADABLE in markdown
    assert "The attached mail is encrypted." in markdown or "The parent stays readable." in markdown
    assert "ENCRYPTED" not in markdown
    assert FastEmailProcessor().extract(FIXTURES / fixture).text


def test_attached_messages_beyond_depth_three_are_listed_by_name_only(tmp_path):
    deepest = _mail("Level 4", "level four body")
    chain = _mail("Level 1", "level one body", [_mail("Level 2", "level two body", [_mail("Level 3", "level three body", [deepest])])])
    markdown = _library_markdown(_write(tmp_path, _mail("Top", "top body", [chain])), tmp_path / "out")

    assert "## Attached message 1.1.1: Level 3" in markdown and "level three body" in markdown
    assert "Attached message 1.1.1.1" not in markdown
    assert "level four body" not in markdown
    assert "### Attachments\n\n- unnamed attachment (" in markdown.split("Attached message 1.1.1: Level 3")[1]


def test_at_most_twenty_attached_messages_are_read(tmp_path):
    msg = _mail("Top", "top body", [_mail(f"Mail {i}", f"body {i}.") for i in range(1, 26)])
    markdown = _library_markdown(_write(tmp_path, msg), tmp_path / "out")

    assert markdown.count("## Attached message ") == 20
    assert "## Attached message 20: Mail 20" in markdown and "body 20." in markdown
    assert "Mail 21" not in markdown and "body 21." not in markdown
    assert markdown.split("## Attached message 1:")[0].count("- unnamed attachment (") == 25


def test_body_cap_covers_parent_and_attached_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.email_processor.email_markdown_processor.LIBRARY_MAX_BODY_CHARS",
        100,
    )
    msg = _mail("Top", "short parent body", [_mail("Long one", "word " * 200), _mail("After the cap", "never shown")])
    markdown = _library_markdown(_write(tmp_path, msg), tmp_path / "out")

    assert "short parent body" in markdown
    assert "## Attached message 1: Long one" in markdown and "## Attached message 2: After the cap" in markdown
    assert markdown.count("_[Body truncated: the message exceeds 100 characters.]_") == 2
    assert markdown.count("word") < 30 and "never shown" not in markdown


def test_attachment_path_cap_covers_the_attached_messages(tmp_path):
    msg = _mail("Top", "short parent body", [_mail("Long one", "word " * 200)])
    file_path = _write(tmp_path, msg)

    full = FastEmailProcessor().extract(file_path)
    assert "## Attached message 1: Long one" in full.text and full.truncated is False

    capped = FastEmailProcessor().extract(file_path, FastTextOptions(max_chars=400))
    assert capped.truncated is True
    assert "short parent body" in capped.text
    assert len(capped.text) <= 402
