// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// The golden corpus: the document text AND its provable answer live together,
// so retrieval has one unambiguous outcome. The marker appears in exactly one
// library, which makes "scoped to A → found" / "scoped to B → absent" a
// deterministic assertion even though a real RAG stack answered.

export const MARKER = "Marchtober";
// A second marker that lives only in BETA. The isolation turn (festival question
// scoped to B) must RETRIEVE B content — proven by echoing this marker — so that
// "MARKER absent" actually means "isolated", not "B retrieval returned nothing".
export const BETA_MARKER = "Gardenbruary";
export const PROBE = "When does the Fredchurro festival take place?";
export const SELF_TEST_AGENT_ID = "fred.github.self_test";

// The prompt journeys assert *delivery* of a prompt the agent echoes back. The
// agent prints `system_prompt: …` / `context_prompt: …`; the harness injects a
// run-scoped marker into each and asserts it comes back. The base marker words
// below are suffixed with the run token in the scenario so they never collide.
export const SYSTEM_PROMPT_MARKER_BASE = "FredSelftestSysprompt";
export const CONTEXT_PROMPT_MARKER_BASE = "FredSelftestCtxprompt";
export const PROMPT_PROBE = "Self-test: confirm the delivered prompts.";

export interface CorpusDoc {
  library: string;
  fileName: string;
  text: string;
}

export const ALPHA: CorpusDoc = {
  library: "fred-selftest-alpha",
  fileName: "fred-selftest-alpha.md",
  text:
    "# Fred self-test fixture ALPHA\n\n" +
    `The Fredchurro festival takes place in ${MARKER}.\n\n` +
    "This sentence is the only place the marker fact appears.\n",
};

export const BETA: CorpusDoc = {
  library: "fred-selftest-beta",
  fileName: "fred-selftest-beta.md",
  text:
    "# Fred self-test fixture BETA\n\n" +
    `This document is about unrelated topics: weather, gardening, and tea, filed under the codeword ${BETA_MARKER}.\n\n` +
    "It deliberately contains no festival information at all.\n",
};

/** Synthesize the upload file from the inline corpus text. */
export function fileOf(doc: CorpusDoc): File {
  return new File([doc.text], doc.fileName, { type: "text/markdown" });
}
