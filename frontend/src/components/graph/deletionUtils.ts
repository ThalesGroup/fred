/// Copyright Thales 2025
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

export const buildChunkToDocMap = (
  // Accept both flat points ({ chunk_id, document_id }) and GraphPoints with metadata
  points: Array<
    | { chunk_uid?: string | number | null; document_uid?: string | number | null }
    | { metadata?: { chunk_uid?: string | number | null; document_uid?: string | number | null } | null }
  >
): Record<string, string> => {
  return (points ?? []).reduce<Record<string, string>>((acc, p: any) => {
    const cid = p?.chunk_uid ?? p?.metadata?.chunk_uid;
    const did = p?.document_uid ?? p?.metadata?.document_uid;
    if (cid != null && did != null) acc[String(cid)] = String(did);
    return acc;
  }, {});
};

export const filterDeletableIds = (selectedIds: string[] | undefined, idToDocMap: Record<string, string>) => {
  return (selectedIds ?? []).filter((id) => !!id && !!idToDocMap[id]);
};

export const removePointsByChunkIds = (
  // Accept both flat points and GraphPoints with metadata
  points: Array<any>,
  successfulIds: Set<string>
) =>
  points.filter((p: any) => {
    const cid = p?.chunk_uid ?? p?.metadata?.chunk_uid;
    return !cid || !successfulIds.has(String(cid));
  });
