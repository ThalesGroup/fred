// Copyright Thales 2025
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

import { KeyCloakService } from "../../security/KeycloakService";
import { DocumentMetadata } from "./knowledgeFlowOpenApi";

export interface ReconcileTagProcessingResult {
  documents: DocumentMetadata[];
  total: number;
}

/**
 * List a folder's documents and reconcile their processing status against Temporal.
 *
 * Same response shape as the library browse endpoint, but the backend additionally
 * checks any still-pending document that carries a workflow id against Temporal and
 * durably marks it FAILED if its workflow is gone/failed/timed-out. This is what
 * guarantees a document never stays "pending in fred" while its Temporal workflow no
 * longer exists. Returned documents always reflect the corrected status.
 *
 * Hand-written (mirrors the streamDocumentUpload convention) so it works without a
 * regenerated client; can be swapped for the generated RTK hook later.
 */
export async function reconcileTagProcessing(args: {
  tagId: string;
  offset: number;
  limit: number;
}): Promise<ReconcileTagProcessingResult> {
  const token = KeyCloakService.GetToken();

  const response = await fetch("/knowledge-flow/v1/documents/processing/reconcile", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ tag_id: args.tagId, offset: args.offset, limit: args.limit }),
  });

  if (!response.ok) {
    throw new Error(`Reconcile failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as ReconcileTagProcessingResult;
}
