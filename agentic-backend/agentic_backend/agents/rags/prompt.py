def grade_documents_prompt() -> str:
    """
    Returns a prompt for a permissive relevance grader in retrieval-augmented generation (RAG).

    Returns:
        str: A formatted prompt string for document relevance grading
    """
    return """
    You are a permissive relevance grader for retrieval-augmented generation (RAG).
    
    Rules :
    - Return 'yes' unless the document is clearly off-topic for the question.
    - Consider shared keywords, entities, acronyms, or overlapping semantics as relevant.
    - Minor mismatches or partial overlaps should still be 'yes'.
    
    Return ONLY valid JSON matching this exact schema: {{"binary_score": "yes"}} or {{"binary_score": "no"}}
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

    QUESTION: {question}
    """


def grade_answer_prompt() -> str:
    """
    Returns a prompt for evaluating whether an answer adequately addresses a given question.

    Returns:
        str: A formatted prompt string for answer relevance grading
    """
    return """
    You are an expert evaluator assessing if an answer adequately responds to a question.

    TASK : Determine if the answer provides useful information that addresses the question.

    EVALUATION PROCESS:
    1. Identify the core intent of the question
    2. Check if the answer contains relevant information about that intent
    3. Verify the answer provides actionable or informative content

    Return "yes" if:
    - The answer directly addresses what was asked
    - It provides specific, concrete information (facts, explanations, steps, examples)
    - A reasonable person would consider their question answered
    - Even if incomplete, the answer contains substantial relevant content

    Return "no" ONLY if:
    - The answer is completely off-topic
    - It only rephrases the question without adding information
    - It's purely conversational without substance (e.g., "That's interesting!")
    - It explicitly says "I don't know" without attempting an answer
    - It's empty or contains only filler words

    IMPORTANT:
    - Don't be overly strict about perfect completeness
    - Focus on whether useful information was provided
    - An answer can be "yes" even if brief, as long as it's relevant and substantive
    - Partial answers that address the main point should be "yes"

    ---

    Question: {question}

    Answer: 
    {generation}

    ---

    Return ONLY valid JSON matching this exact schema: {{"binary_score": "yes"}} or {{"binary_score": "no"}}
    """
