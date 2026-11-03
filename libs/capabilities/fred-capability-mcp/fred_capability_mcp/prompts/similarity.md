## Document comparison (similar passages in named documents or folders)

`find_similar_passages` returns the passages most similar to an `anchor`
text, ranked best-first, from the documents and library folders you name.
It compares; it does not answer open questions over the whole corpus.

- Pass the text to compare as `anchor`: a requirement, a clause, a
  paragraph, a question restated as a statement.
- Name at least one target: `document_uids` and/or
  `document_library_tags_ids`. A call without a target is rejected, and a
  target the user cannot read is refused.
- `top_k` bounds the number of passages (default 10). Keep `rerank` on
  unless speed matters more than ordering.
- Scores rank passages within one call; they are not probabilities. Use
  `min_score` only to drop clearly weak matches.
- Fewer passages, including none, is a valid answer: say that no similar
  passage was found rather than inventing one.

Cite the document title and page or section of each passage you rely on.
