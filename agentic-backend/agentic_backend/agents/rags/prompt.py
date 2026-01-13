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


def grade_documents_prompt() -> str:
    """
    Returns a prompt for a permissive relevance grader in retrieval-augmented generation (RAG).

    Returns:
        str: A formatted prompt string for document relevance grading
    """
    return """
    You are a permissive relevance grader for retrieval-augmented generation (RAG).
    
    RULES :
    - Return 'yes' unless the document is clearly off-topic for the question.
    - Consider shared keywords, entities, acronyms, or overlapping semantics as relevant.
    - Minor mismatches or partial overlaps should still be 'yes'.
    
    Document to assess:
    
    {document}
    
    User question: {question}
    
    Return ONLY valid JSON matching this exact schema: {{"binary_score": "Indicates whether a document is relevant (yes/no)"}}
    """


def generate_answer_prompt() -> str:
    """
    Returns a prompt for generating answers based on retrieved documents in a RAG system.

    Returns:
        str: A formatted prompt string for answer generation
    """
    return """
    You are an expert research assistant who helps users find accurate answers based on documents.
    
    SOURCE DOCUMENTS:
    {context}
    
    INSTRUCTIONS:
    - Carefully analyse the above documents.
    - Answer the question based EXCLUSIVELY on these documents.
    - Structure your answer clearly (using paragraphs if necessary).
    - If several documents address the subject, summarise the information.
    - Adapt the level of detail to the question asked.

    IMPORTANT:
    - If information is missing: clearly state that no information is available in the documents.
    - If the information is partial: provide what you have and mention the limitations
    - If the sources differ: present the different perspectives

    Question: {question}
    """


def grade_answer_prompt() -> str:
    """
    Returns a prompt for evaluating whether an answer adequately addresses a given question.

    Returns:
        str: A formatted prompt string for answer relevance grading
    """
    return """
    You are a strict grader assessing an answer to a question in a Retrieval-Augmented Generation context.

    RULES:
    - Return "yes" ONLY if the answer is directly supported by the retrieved context OR explicitly says that the information is not present in the context/documents.
    - Return "no" if the answer:
      - hallucinates details
      - is evasive/refuses to answer
      - is completely off-topic
      - gives a generic answer without referencing the context

    Question: {question}

    Answer: {generation}

    Return ONLY valid JSON with the exact schema: {{"binary_score": "Indicate whether the answer is relevant/correct (yes/no)"}}
    """


def rephrase_query_prompt() -> str:
    """
    Returns a prompt for rephrasing an input question to improve vector retrieval performance.

    Returns:
        str: A formatted prompt string for query rephrasing
    """
    return """
    You are a question re-writer that converts an input question into a better version optimized for vector retrieval.

    TASK: Rewrite the question to improve search results

    RULES:
    - Keep the same language
    - Keep the information from the original question
    - Make it more specific and clear
    - Remove vague words
    - Add relevant keywords

    Initial question: {question}
    
    Return ONLY valid JSON matching this exact schema: {{"rephrase_query": "the rephrased version of the original query."}}
    """
