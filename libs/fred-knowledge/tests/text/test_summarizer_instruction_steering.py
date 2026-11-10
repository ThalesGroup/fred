# Copyright Thales 2025
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

from typing import List, Optional

from fred_knowledge.text.base_summarizer import BaseDocSummarizer
from fred_knowledge.text.base_text_splitter import BaseTextSplitter
from fred_knowledge.text.llm_summarizer import LLMBasedDocSummarizer
from fred_knowledge.text.smart_llm_summarizer import SmartDocSummarizer
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel


class _FixedWidthSplitter(BaseTextSplitter):
    """Splits text into fixed-size shards so map-reduce is exercised deterministically."""

    def __init__(self, shard_size: int = 200):
        self.shard_size = shard_size

    def split(self, document: Document) -> List[Document]:
        text = document.page_content or ""
        return [Document(page_content=text[i : i + self.shard_size], metadata={}) for i in range(0, len(text), self.shard_size)] or [document]


class _RecordingSummarizer(BaseDocSummarizer):
    """Fake summarizer that records every (text, instruction) pair it was asked to summarize."""

    def __init__(self):
        self.abstract_calls: List[tuple[str, Optional[str]]] = []
        self.token_calls = 0

    def summarize_abstract(self, text: str, *, max_words: int = 180, instruction: Optional[str] = None) -> str:
        self.abstract_calls.append((text, instruction))
        return f"summary of {len(text)} chars"

    def summarize_tokens(self, text: str, *, top_k: int = 24, vocab_hint: Optional[str] = None) -> List[str]:
        self.token_calls += 1
        return ["kw"]


def _smart_summarizer_with_fake(*, opts: Optional[dict] = None) -> tuple[SmartDocSummarizer, _RecordingSummarizer]:
    """Build a SmartDocSummarizer with its admitted model swapped for a recording fake."""
    smart = SmartDocSummarizer(model=FakeListChatModel(responses=["unused"]), model_name="fake", splitter=_FixedWidthSplitter(), opts=opts)
    fake = _RecordingSummarizer()
    smart._summarizer = fake
    return smart, fake


def test_single_pass_skips_reduce_and_forwards_instruction():
    """A small document (below small_threshold) takes one map call, no reduce."""
    smart, fake = _smart_summarizer_with_fake(opts={"small_threshold": 10_000})
    doc = Document(page_content="short document content", metadata={})

    abstract, _ = smart.summarize_document(doc, instruction="focus on risks")

    assert len(fake.abstract_calls) == 1
    assert fake.abstract_calls[0][1] == "focus on risks"
    assert abstract == f"summary of {len(doc.page_content)} chars"


def test_single_pass_compute_keywords_false_skips_keyword_call():
    """On-demand callers can skip the separate keyword-extraction LLM call to halve
    round-trips; the abstract is still produced and keywords come back empty."""
    smart, fake = _smart_summarizer_with_fake(opts={"small_threshold": 10_000})
    doc = Document(page_content="short document content", metadata={})

    abstract, keywords = smart.summarize_document(doc, compute_keywords=False)

    assert len(fake.abstract_calls) == 1  # abstract still computed
    assert fake.token_calls == 0  # keyword call skipped
    assert keywords == []


def test_single_pass_compute_keywords_true_calls_keyword_extraction():
    """Default (ingestion) behavior still computes keywords."""
    smart, fake = _smart_summarizer_with_fake(opts={"small_threshold": 10_000})
    doc = Document(page_content="short document content", metadata={})

    _, keywords = smart.summarize_document(doc)

    assert fake.token_calls == 1
    assert keywords == ["kw"]


def test_map_reduce_compute_keywords_false_skips_keyword_call():
    """Map-reduce path also honors compute_keywords=False."""
    smart, fake = _smart_summarizer_with_fake(opts={"small_threshold": 10, "large_threshold": 1_000_000, "mr_top_shards": 10})
    doc = Document(page_content="x" * 1000, metadata={})

    _, keywords = smart.summarize_document(doc, compute_keywords=False)

    assert fake.token_calls == 0
    assert keywords == []


def test_map_reduce_forwards_instruction_to_every_shard_and_the_reduce_call():
    """A large document takes the map-reduce path; every map call and the final
    reduce call must receive the same instruction."""
    smart, fake = _smart_summarizer_with_fake(opts={"small_threshold": 10, "large_threshold": 1_000_000, "mr_top_shards": 10})
    doc = Document(page_content="x" * 1000, metadata={})

    smart.summarize_document(doc, instruction="list every action item")

    assert len(fake.abstract_calls) > 1  # at least one map call + the reduce call
    assert all(instruction == "list every action item" for _, instruction in fake.abstract_calls)


def test_no_instruction_preserves_default_behavior():
    """Calling without an instruction (the ingestion-time path) still works and
    passes instruction=None through, unchanged from before this feature."""
    smart, fake = _smart_summarizer_with_fake(opts={"small_threshold": 10_000})
    doc = Document(page_content="short document content", metadata={})

    smart.summarize_document(doc)

    assert fake.abstract_calls[0][1] is None


def test_llm_based_summarizer_blends_instruction_into_prompt(monkeypatch):
    """LLMBasedDocSummarizer.summarize_abstract should use the instruction-aware
    prompt branch when instruction is set, and the default abstract prompt otherwise."""
    captured: dict[str, str] = {}

    def fake_complete(self, system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return "ok"

    monkeypatch.setattr(LLMBasedDocSummarizer, "_complete", fake_complete, raising=True)
    summarizer = LLMBasedDocSummarizer.__new__(LLMBasedDocSummarizer)  # bypass __init__ (no real model)

    summarizer.summarize_abstract("some text", max_words=50, instruction="focus on financial risks")
    assert "focus on financial risks" in captured["user"]

    summarizer.summarize_abstract("some text", max_words=50)
    assert "concise abstract" in captured["user"]
    assert "focus on financial risks" not in captured["user"]
