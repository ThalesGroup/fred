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

import { useCreateTagMutation } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { MAX_FOLDER_DEPTH } from "@shared/organisms/DocumentUploadDrawer/droppedPaths";
import FolderNameDialog from "./FolderNameDialog";

interface CreateFolderModalProps {
  open: boolean;
  onClose: () => void;
  /** Parent folder full path, e.g. "CIR" or "CIR/Sub". `undefined` => top level. */
  parentPath?: string;
  /** Team id for a collaborative team; omit/undefined for the personal space. */
  teamId?: string;
  /**
   * Optional custom create handler. When provided it is used instead of creating a corpus
   * library (e.g. a team-rooted /fs `mkdir`); the corpus behaviour is the default.
   */
  onSubmit?: (name: string) => Promise<void>;
  onCreated: () => void;
}

// Legacy corpus callers retain their transport; the dialog owns only interaction.
export default function CreateFolderModal({ teamId, onSubmit, ...props }: CreateFolderModalProps) {
  const [createTag] = useCreateTagMutation();
  return (
    <FolderNameDialog
      {...props}
      maxDepth={onSubmit ? null : MAX_FOLDER_DEPTH}
      onSubmit={
        onSubmit ??
        (async (name) => {
          await createTag({
            tagCreate: { name, path: props.parentPath ?? null, type: "document", team_id: teamId ?? null },
          }).unwrap();
        })
      }
    />
  );
}
