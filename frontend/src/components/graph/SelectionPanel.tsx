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

import React, { useMemo } from "react";
import { Stack, Typography } from "@mui/material";
import ChunksAccordion from "../documents/data/ChunksAccordion.tsx";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";

type ChunkRef = { document_uid: string; chunk_uid: string; text?: string };

export const SelectionPanel: React.FC<{
  idToDocMap: Record<string, string>;
  idToTextMap?: Record<string, string>;
  selectedIds: string[];
  handleDeleteSelection: () => void;
  isDeleting: boolean;
  t: (k: string, fallback?: string) => string;
}> = ({ idToDocMap, idToTextMap, selectedIds, handleDeleteSelection, isDeleting, t }) => {
  const selectedChunks = useMemo<ChunkRef[]>(() => {
    const uniq = Array.from(new Set(selectedIds ?? []));
    return uniq
      .map((cid) => ({
        document_uid: idToDocMap[cid],
        chunk_uid: cid,
        text: idToTextMap ? idToTextMap[cid] : undefined,
      }))
      .filter((x) => x.document_uid && x.chunk_uid);
  }, [selectedIds, idToDocMap, idToTextMap]);

  return (
    <Stack spacing={1.5}>
      {/* Selection section */}
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">{t("graphHub.selection.title", "Selection")}</Typography>
        <DeleteIconButton
          size="small"
          title={t("graphHub.deleteSelection", "Delete selection")}
          onClick={handleDeleteSelection}
          disabled={isDeleting}
        />
      </Stack>
      <ChunksAccordion chunks={selectedChunks} />
    </Stack>
  );
};

export default SelectionPanel;
