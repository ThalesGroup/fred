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

import { DocumentMetadata } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

// The Name column always shows document_name: identity.title is populated
// ingestion-time straight from the file's own embedded metadata
// (PDF /Title, docx core_properties.title) with no validation, so it's as
// likely to be empty, a stale value copied from a shared template, or a
// generic "Untitled" placeholder as it is a real paper/document title.
export function documentDisplayName(doc: DocumentMetadata): string {
  return doc.identity.document_name;
}

// Surfaced as a hint next to the filename, not as the primary label: still
// useful (e.g. an arXiv PDF's real paper title) when it isn't just noise —
// filtered out when blank or when it doesn't actually add anything over the
// filename itself (base_input_processor.py defaults title to the filename
// stem, so most never-renamed, no-metadata documents would otherwise show an
// identical-looking hint).
export function embeddedTitle(doc: DocumentMetadata): string | null {
  const title = doc.identity.title?.trim();
  if (!title) return null;
  const stem = doc.identity.document_name.replace(/\.[^./]+$/, "");
  return title === doc.identity.document_name || title === stem ? null : title;
}
