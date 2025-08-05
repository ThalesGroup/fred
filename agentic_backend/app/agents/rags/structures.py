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
from langchain_core.messages import BaseMessage
from langgraph.graph.message import MessagesState
from app.common.document_source import DocumentSource
from app.core.chatbot.chat_schema import ChatSource

class RAGState(MessagesState):
    messages: List[BaseMessage]
    rewritten_question: Optional[str]
    retrieved_documents: List[DocumentSource]
    sources: List[ChatSource]
