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
import { useMemo } from "react";
import { knowledgeFlowApi } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { KnowledgeDeps } from "../scenarios/knowledgeScenario";
import type { PipelineDeps } from "../types";
import { FRESH, useApiDispatch } from "./api";

// Fixtures live in the personal space, so every scoped call says so.
const PERSONAL = "personal" as const;

/** Extends the shared base deps, so the page keeps one set of product hooks. */
export function useKnowledgeDeps(base: PipelineDeps): KnowledgeDeps {
  const dispatch = useApiDispatch();
  return useMemo(() => {
    const kf = knowledgeFlowApi.endpoints;
    const setMembers = async (tagId: string, change: (ids: string[]) => string[]) => {
      const tag = await dispatch(kf.getTag.initiate({ tagId }, FRESH)).unwrap();
      await dispatch(
        kf.updateTag.initiate({
          tagId,
          tagUpdate: {
            name: tag.name,
            path: tag.path,
            description: tag.description,
            type: tag.type,
            item_ids: change(tag.item_ids),
          },
        }),
      ).unwrap();
    };
    return {
      ...base,
      documentsIn: async (libraryId) => {
        const page = await dispatch(
          kf.browseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePost.initiate({
            browseDocumentsByTagRequest: { tag_id: libraryId, limit: 200 },
          }),
        ).unwrap();
        return page.documents.map((d) => ({ uid: d.identity.document_uid, name: d.identity.document_name }));
      },
      search: async ({ question, libraryIds, documentUids, policy }) => {
        const hits = await dispatch(
          kf.searchDocumentsUsingVectorization.initiate({
            searchRequest: {
              question,
              top_k: 10,
              document_library_tags_ids: libraryIds ?? null,
              document_uids: documentUids ?? null,
              search_policy: policy ?? null,
              owner_filter: PERSONAL,
            },
          }),
        ).unwrap();
        return hits.map((h) => ({ uid: h.uid, content: h.content }));
      },
      linkDocument: (libraryId, uid) => setMembers(libraryId, (ids) => [...new Set([...ids, uid])]),
      unlinkDocument: (libraryId, uid) => setMembers(libraryId, (ids) => ids.filter((id) => id !== uid)),
      setRetrievable: async (uid, retrievable) => {
        await dispatch(
          kf.updateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPut.initiate({
            documentUid: uid,
            retrievable,
          }),
        ).unwrap();
      },
      documentTree: async (libraryId) => {
        const response = await dispatch(
          kf.getDocumentTreeKnowledgeFlowV1DocumentsTreePost.initiate({
            documentTreeRequest: { tag_ids: [libraryId], owner_filter: PERSONAL },
          }),
        ).unwrap();
        return response.tree;
      },
      tabularRows: async (libraryId, uid, sql) => {
        // The listing carries table aliases for spreadsheets only; the schemas carry them for every kind.
        const [described] = await dispatch(
          kf.describeTabularDocuments.initiate(
            { documentUids: [uid], documentLibraryTagsIds: [libraryId], ownerFilter: PERSONAL },
            FRESH,
          ),
        ).unwrap();
        const alias = described?.tables?.[0]?.query_alias;
        if (!alias) throw new Error("the document exposes no queryable table");
        const result = await dispatch(
          kf.readQuery.initiate({
            tabularQueryRequest: {
              sql: sql(alias),
              dataset_uids: [uid],
              document_library_tags_ids: [libraryId],
              owner_filter: PERSONAL,
              max_rows: 10,
            },
          }),
        ).unwrap();
        if (result.error) throw new Error(`SQL error: ${result.error}`);
        return result.rows ?? [];
      },
      audit: async () => {
        const report = await dispatch(kf.auditDocumentsKnowledgeFlowV1DocumentsAuditGet.initiate({}, FRESH)).unwrap();
        return (report.anomalies ?? []).map((a) => ({ uid: a.document_uid, issues: a.issues ?? [] }));
      },
      sleep: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
    };
  }, [base, dispatch]);
}
