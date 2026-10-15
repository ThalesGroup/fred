# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""Live document isolation and lifecycle, with positive retrieval controls."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
from document_probe import (
    PROBE,
    ApiClient,
    ClientFactory,
    Json,
    assert_found,
    checked,
    final_event,
    hit_uids,
    ingest,
    library,
    runtime_events,
    search,
    unlink,
    wait_indexed,
    wait_until,
)
from factory_config import RUNTIME_PUBLIC_BASE, TEST_TEAM, USERS
from fred_sdk.contracts import RuntimeExecuteRequest
from fred_sdk.contracts.context import RuntimeContext

POLICIES = ["semantic", "hybrid", "strict"]


@dataclass
class Corpus:
    editor: str
    reader: str
    other_reader: str
    team_a: str
    team_b: str
    a: Json
    b: Json
    uid_a: str
    uid_b: str
    marker_a: str
    marker_b: str
    uid_unselected: str
    marker_unselected: str


@pytest.fixture(scope="module")
def corpus(cp: ClientFactory, kf: ClientFactory) -> Iterator[Corpus]:
    # Choose existing demo roles; never mutate memberships to make a test pass.
    candidates = [
        (editor, other, reader, other_reader)
        for editor, user in USERS.items()
        if user.is_team_editor_in(TEST_TEAM)
        for other in sorted(user.teams)
        if other != TEST_TEAM and user.is_team_editor_in(other)
        for reader, member in USERS.items()
        if TEST_TEAM in member.teams and other not in member.teams
        for other_reader, other_member in USERS.items()
        if other in other_member.teams and TEST_TEAM not in other_member.teams
    ]
    assert candidates, (
        "Demo fixtures need a two-team editor and one exclusive reader in each team"
    )
    editor, other, reader, other_reader = candidates[0]
    teams = checked(cp(editor).get("/teams")).json()
    ids = {t["name"]: t.get("id") or t.get("team_id") for t in teams}
    team_a, team_b = ids[TEST_TEAM], ids[other]
    client = kf(editor)
    with ExitStack() as cleanup:
        a = cleanup.enter_context(library(client, team_a))
        b = cleanup.enter_context(library(client, team_b))
        marker_a, marker_b = f"ALPHA{uuid4().hex}", f"BETA{uuid4().hex}"
        uid_a = ingest(client, [a["id"]], marker_a)
        uid_b = ingest(client, [b["id"]], marker_b)
        marker_unselected = f"UNSELECTED{uuid4().hex}"
        uid_unselected = ingest(client, [a["id"]], marker_unselected)
        wait_indexed(
            client,
            team_id=team_a,
            library_id=a["id"],
            uid=uid_unselected,
            marker=marker_unselected,
        )
        wait_indexed(
            client, team_id=team_a, library_id=a["id"], uid=uid_a, marker=marker_a
        )
        wait_indexed(
            client, team_id=team_b, library_id=b["id"], uid=uid_b, marker=marker_b
        )
        yield Corpus(
            editor,
            reader,
            other_reader,
            team_a,
            team_b,
            a,
            b,
            uid_a,
            uid_b,
            marker_a,
            marker_b,
            uid_unselected,
            marker_unselected,
        )


@pytest.mark.parametrize("policy", POLICIES)
def test_library_scope_isolates_two_readable_teams(
    corpus: Corpus, kf: ClientFactory, policy: str
) -> None:
    """A user in two teams retrieves each team's document only in that team's library scope."""
    c = corpus
    for team, tag, uid, marker, forbidden in (
        (c.team_a, c.a, c.uid_a, c.marker_a, c.uid_b),
        (c.team_b, c.b, c.uid_b, c.marker_b, c.uid_a),
    ):
        hits = search(kf(c.editor), team_id=team, libraries=[tag["id"]], policy=policy)
        assert_found(hits, uid, marker)
        assert forbidden not in hit_uids(hits)


@pytest.mark.parametrize("policy", POLICIES)
def test_explicit_document_cannot_escape_active_team(
    corpus: Corpus, kf: ClientFactory, policy: str
) -> None:
    """A personally readable B document selected by UID is excluded in active team A."""
    c = corpus
    assert_found(
        search(kf(c.editor), team_id=c.team_b, documents=[c.uid_b], policy=policy),
        c.uid_b,
        c.marker_b,
    )
    assert (
        search(kf(c.editor), team_id=c.team_a, documents=[c.uid_b], policy=policy) == []
    )


@pytest.mark.parametrize("policy", POLICIES)
def test_mixed_library_and_document_selection_stays_in_team(
    corpus: Corpus, kf: ClientFactory, policy: str
) -> None:
    """Combining an A library with a readable B UID returns A content without admitting B."""
    c = corpus
    hits = search(
        kf(c.editor),
        team_id=c.team_a,
        libraries=[c.a["id"]],
        documents=[c.uid_b],
        policy=policy,
    )
    assert_found(hits, c.uid_a, c.marker_a)
    assert c.uid_b not in hit_uids(hits)


@pytest.mark.parametrize("policy", POLICIES)
def test_document_only_selection_does_not_widen(
    corpus: Corpus, kf: ClientFactory, policy: str
) -> None:
    """A document-only selection returns that document, without widening to other readable documents."""
    c = corpus
    baseline = search(
        kf(c.editor), team_id=c.team_a, libraries=[c.a["id"]], policy=policy
    )
    assert_found(baseline, c.uid_a, c.marker_a)
    assert_found(baseline, c.uid_unselected, c.marker_unselected)
    hits = search(kf(c.editor), team_id=c.team_a, documents=[c.uid_a], policy=policy)
    assert_found(hits, c.uid_a, c.marker_a)
    assert hit_uids(hits) == {c.uid_a}


@pytest.mark.parametrize("selection", ["document", "library"])
def test_denied_selection_returns_no_corpus(
    corpus: Corpus, kf: ClientFactory, selection: str
) -> None:
    """A forbidden explicit {selection} does not fall back to the reader's authorized corpus."""
    c = corpus
    client = kf(c.reader)
    assert_found(
        search(client, team_id=c.team_a, libraries=[c.a["id"]]), c.uid_a, c.marker_a
    )
    hits = search(
        client,
        team_id=c.team_a,
        documents=[c.uid_b] if selection == "document" else None,
        libraries=[c.b["id"]] if selection == "library" else None,
    )
    assert hits == []


@pytest.mark.parametrize("surface", ["metadata", "chunks"])
def test_foreign_document_direct_read_is_denied(
    corpus: Corpus, kf: ClientFactory, surface: str
) -> None:
    """A reader outside B cannot fetch B's document through {surface}, even knowing its UID."""
    c = corpus
    path = (
        f"/documents/metadata/{c.uid_b}"
        if surface == "metadata"
        else "/vector/document-chunks"
    )
    params = {} if surface == "metadata" else {"document_uid": c.uid_b}
    checked(kf(c.other_reader).get(path, params=params))
    assert kf(c.reader).get(path, params=params).status_code in (403, 404)


@pytest.fixture(scope="module")
def revoked(corpus: Corpus, kf: ClientFactory) -> Iterator[tuple[str, str, str]]:
    c = corpus
    client = kf(c.editor)
    with library(client, c.team_a) as a, library(client, c.team_b) as b:
        marker = f"SHARED{uuid4().hex}"
        uid = ingest(client, [a["id"], b["id"]], marker)
        # Establish both indexed links and the reader's permission before removal.
        for user, team, tag in ((c.reader, c.team_a, a), (c.other_reader, c.team_b, b)):
            wait_indexed(
                kf(user), team_id=team, library_id=tag["id"], uid=uid, marker=marker
            )
            checked(kf(user).get(f"/documents/metadata/{uid}"))
        unlink(client, a, uid)
        metadata = checked(client.get(f"/documents/metadata/{uid}")).json()
        assert set(metadata["tags"]["tag_ids"]) == {b["id"]}
        assert_found(
            search(kf(c.other_reader), team_id=c.team_b, libraries=[b["id"]]),
            uid,
            marker,
        )
        yield uid, marker, a["id"]


@pytest.mark.parametrize("policy", POLICIES)
def test_revoked_document_absent_from_library_search(
    corpus: Corpus, revoked: tuple[str, str, str], kf: ClientFactory, policy: str
) -> None:
    """After removing A's link, A's reader cannot retrieve the document through its old library ({policy})."""
    uid, marker, tag_id = revoked
    hits = search(
        kf(corpus.reader), team_id=corpus.team_a, libraries=[tag_id], policy=policy
    )
    assert uid not in hit_uids(hits) and all(
        marker not in h.get("content", "") for h in hits
    ), f"Revoked document {uid} leaked through former library {tag_id}"


@pytest.mark.parametrize("surface", ["metadata", "chunks", "document_search"])
def test_revocation_also_blocks_direct_read(
    corpus: Corpus, revoked: tuple[str, str, str], kf: ClientFactory, surface: str
) -> None:
    """After removing A's link, direct {surface} access is revoked for A's reader."""
    uid, _, _ = revoked
    client = kf(corpus.reader)
    if surface == "document_search":
        assert search(client, team_id=corpus.team_a, documents=[uid]) == []
    else:
        path = (
            f"/documents/metadata/{uid}"
            if surface == "metadata"
            else "/vector/document-chunks"
        )
        params = {} if surface == "metadata" else {"document_uid": uid}
        assert client.get(path, params=params).status_code in (403, 404)


@dataclass
class Conversation:
    client: ApiClient
    team_id: str
    instance_id: str
    session_id: str
    token: Callable[[], str]

    def turn(
        self,
        *,
        libraries: list[str] | None = None,
        documents: list[str] | None = None,
        attachments: str | None = None,
        corpus: bool = True,
    ) -> Json:
        prep = checked(
            self.client.post(
                f"/teams/{self.team_id}/agent-instances/{self.instance_id}/prepare-execution",
                params={"session_id": self.session_id},
            )
        ).json()
        path = prep["execute_stream_url"]
        assert path.startswith("/") and not path.startswith("//"), (
            "Expected an ingress-relative runtime URL"
        )
        request = RuntimeExecuteRequest(
            agent_instance_id=self.instance_id,
            session_id=self.session_id,
            input="document " + PROBE,
            runtime_context=RuntimeContext(
                team_id=self.team_id,
                selected_document_libraries_ids=libraries,
                selected_document_uids=documents,
                attachments_markdown=attachments,
                search_policy="semantic",
                include_session_scope=attachments is not None,
                include_corpus_scope=corpus,
            ),
        )

        def execute(body: RuntimeExecuteRequest) -> httpx.Response:
            return httpx.post(
                RUNTIME_PUBLIC_BASE + path,
                headers={
                    "Authorization": f"Bearer {self.token()}",
                    "Accept": "text/event-stream",
                },
                json=body.model_dump(mode="json"),
                timeout=90,
                follow_redirects=False,
            )

        response = execute(request)
        events = runtime_events(response)
        assert any(
            e.get("kind") == "tool_result"
            and e.get("tool_name") == "search_documents_using_vectorization"
            for e in events
        ), (
            "The document capability did not execute; an empty answer cannot prove isolation"
        )
        pauses = [e["request"] for e in events if e.get("kind") == "awaiting_human"]
        if pauses:
            assert (
                len(pauses) == 1 and pauses[0].get("stage") == "test_document_confirm"
            ), "Unexpected agent pause"
            pause = pauses[0]
            assert pause.get("interrupt_id"), (
                "Confirmation pause has no interrupt identity"
            )
            request = request.model_copy(
                update={
                    "interrupt_id": pause["interrupt_id"],
                    "occurrence_id": pause.get("occurrence_id"),
                    "resume_payload": {"answer": "confirm", "choice_id": "confirm"},
                }
            )
            response = execute(request)
        return final_event(response)


@pytest.fixture
def conversation(
    corpus: Corpus, cp: ClientFactory, token_for: Callable[[str], str]
) -> Iterator[Conversation]:
    c = corpus
    editor = cp(c.editor)
    templates = checked(editor.get(f"/teams/{c.team_a}/agent-templates")).json()
    template = next(
        (t for t in templates if t["source_agent_id"] == "fred.github.test_assistant"),
        None,
    )
    assert template, (
        "Test Assistant is unavailable to this team. Check the deployed runtime "
        "and enable fred.github.test_assistant in Admin > Features for the test team."
    )
    assert any(
        entry.get("id") == "document_access"
        for entry in template.get("available_capabilities", [])
    ), (
        "The document_access capability must be installed and enabled for the validation team"
    )
    created = checked(
        editor.post(
            f"/teams/{c.team_a}/agent-instances",
            json={
                "template_id": template["template_id"],
                "display_name": f"Validation-{uuid4().hex}",
                "usage_statement": "Temporary deterministic document-access validation.",
                "capability_ids": ["document_access"],
                "capability_config_values": {
                    "document_access": {
                        "attachments": True,
                        "team_documents": True,
                        "min_source_score_ratio": 0,
                    }
                },
                "tuning_field_values": {"settings.delay_ms": 0},
            },
        )
    ).json()
    instance = created["agent_instance_id"]
    try:
        client = cp(c.editor)
        sid = str(uuid4())
        checked(
            client.post(
                f"/teams/{c.team_a}/sessions",
                json={
                    "session_id": sid,
                    "agent_instance_id": instance,
                    "title": "Document validation",
                },
            )
        )
        try:
            yield Conversation(
                client, c.team_a, instance, sid, lambda: token_for(c.editor)
            )
        finally:
            checked(client.delete(f"/teams/{c.team_a}/sessions/{sid}"))
    finally:
        checked(editor.delete(f"/teams/{c.team_a}/agent-instances/{instance}"))


def test_runtime_uid_selection_respects_active_team(
    corpus: Corpus, conversation: Conversation
) -> None:
    """The real runtime retrieves an A document, then excludes a readable B UID in the same A session."""
    c = corpus
    assert_found(conversation.turn(documents=[c.uid_a])["sources"], c.uid_a, c.marker_a)
    final = conversation.turn(documents=[c.uid_b])
    assert c.uid_b not in hit_uids(
        final.get("sources", [])
    ) and c.marker_b not in final.get("content", "")


def test_new_library_document_reaches_existing_conversation(
    corpus: Corpus, conversation: Conversation, kf: ClientFactory
) -> None:
    """A second turn in the same session retrieves a document ingested after the first turn."""
    c = corpus
    with library(kf(c.editor), c.team_a) as tag:
        marker = f"LATE{uuid4().hex}"
        before = conversation.turn(libraries=[tag["id"]])
        assert before.get("sources", []) == [] and marker not in before.get(
            "content", ""
        )
        uid = ingest(kf(c.editor), [tag["id"]], marker)
        wait_indexed(
            kf(c.editor), team_id=c.team_a, library_id=tag["id"], uid=uid, marker=marker
        )
        assert_found(conversation.turn(libraries=[tag["id"]])["sources"], uid, marker)


@pytest.mark.parametrize(
    "corpus_selection", [False, True], ids=["session-only", "session-and-document"]
)
def test_late_attachment_and_session_isolation(
    corpus: Corpus,
    conversation: Conversation,
    kf: ClientFactory,
    corpus_selection: bool,
) -> None:
    """A late attachment reaches the next turn and stays session-private, including corpus selection={corpus_selection}."""
    c, conv = corpus, conversation
    client = kf(c.editor)
    before = conv.turn(attachments="", corpus=False)
    assert before.get("sources", []) == []
    marker = f"ATTACHMENT{uuid4().hex}"
    filename = f"validation-{uuid4().hex}.md"
    attachment = checked(
        client.post(
            "/fast/ingest",
            files={
                "file": (
                    filename,
                    f"The validation observatory access code is {marker}.",
                    "text/markdown",
                )
            },
            data={"session_id": conv.session_id, "scope": "session"},
            timeout=180,
        )
    ).json()
    uid = attachment["document_uid"]
    try:
        wait_until(
            lambda: (
                uid
                in hit_uids(
                    search(
                        client,
                        team_id=c.team_a,
                        session_id=conv.session_id,
                        corpus=False,
                    )
                )
            ),
            description=f"attachment index visibility for {uid}",
            timeout=30,
        )
        assert_found(
            conv.turn(
                attachments=f"- {filename} [{uid}]: conversation document", corpus=False
            )["sources"],
            uid,
            marker,
        )
        assert (
            search(client, team_id=c.team_a, session_id=str(uuid4()), corpus=False)
            == []
        )
        assert (
            search(
                kf(c.reader), team_id=c.team_a, session_id=conv.session_id, corpus=False
            )
            == []
        )
        if corpus_selection:
            sources = conv.turn(
                attachments=f"- {filename} [{uid}]: conversation document",
                documents=[c.uid_a],
            )["sources"]
            assert_found(sources, uid, marker)
            assert_found(sources, c.uid_a, c.marker_a)
            # Also exercise the public search API independently of runtime scope resolution.
            assert_found(
                search(
                    client,
                    team_id=c.team_a,
                    session_id=conv.session_id,
                    documents=[c.uid_a],
                ),
                uid,
                marker,
            )
    finally:
        checked(
            client.delete(
                f"/fast/delete/{uid}",
                params={"session_id": conv.session_id},
                timeout=90,
            )
        )
