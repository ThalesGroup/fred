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

from abc import ABC, abstractmethod
from typing import List, Optional


class BaseDocSummarizer(ABC):
    """
    Fred rationale:
    - Standard contract for all summarizers (LLM-based, extractive, smart orchestrator).
    - Keeps pipeline decoupled from concrete implementations.
    """

    @abstractmethod
    def summarize_abstract(self, text: str, *, max_words: int = 180) -> str:
        """
        Human-readable summary (abstract style).
        - Max length is advisory, not strict.
        - Should return a coherent paragraph.
        """
        raise NotImplementedError

    @abstractmethod
    def summarize_tokens(self, text: str, *, top_k: int = 24, vocab_hint: Optional[str] = None) -> List[str]:
        """
        Token summary tuned for retrieval enrichment (keywords/phrases).
        - Prefer multi-word phrases when salient (e.g., 'vector clock', 'LangGraph recursion').
        - Output lowercased, de-duplicated.
        """
        raise NotImplementedError
