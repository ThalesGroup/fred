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

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { OptionModel } from "@models/Option.model.ts";
import {
  useLsQuery,
  useMkdirMutation,
  useUploadFileMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";

type AddAction = "file" | "folder";

interface FsRootAddMenuProps {
  /** Team-rooted base path for the area; uploads/folders are created at its top level. */
  root: string;
}

/**
 * The discreet "+" add control for one /fs root (Mon espace / Espace d'équipe).
 *
 * Self-contained: it owns the file input and the new-folder modal, and refreshes the shared
 * `ls(root)` cache so the area body and the root's count marker update in place. Reuses the
 * app's IconButtonMenu popover (Add a file / New folder).
 */
export default function FsRootAddMenu({ root }: FsRootAddMenuProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [newFolderOpen, setNewFolderOpen] = useState(false);

  const { refetch } = useLsQuery({ path: root });
  const [uploadFile] = useUploadFileMutation();
  const [mkdir] = useMkdirMutation();

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);
      await uploadFile({ path: `${root}/${file.name}`, bodyUploadFile: formData as never }).unwrap();
    }
    refetch();
  };

  const handleMkdir = async (name: string) => {
    await mkdir({ path: `${root}/${name}` }).unwrap();
    refetch();
  };

  const options: OptionModel<AddAction>[] = [
    {
      key: "file",
      value: "file",
      label: t("rework.resources.menu.addFile"),
      icon: { category: "outlined", type: "attach_file" },
    },
    {
      key: "folder",
      value: "folder",
      label: t("rework.resources.menu.newFolder"),
      icon: { category: "outlined", type: "create_new_folder" },
    },
  ];

  return (
    <>
      <IconButtonMenu
        iconButton={{
          color: "on-surface",
          variant: "outlined",
          size: "xs",
          icon: { category: "outlined", type: "add" },
        }}
        options={options}
        onSelect={(value: AddAction) => {
          if (value === "file") fileInputRef.current?.click();
          else setNewFolderOpen(true);
        }}
      />
      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        onChange={(event) => {
          void handleUpload(event.target.files);
          event.target.value = "";
        }}
      />
      <CreateFolderModal
        open={newFolderOpen}
        onClose={() => setNewFolderOpen(false)}
        onSubmit={handleMkdir}
        onCreated={() => refetch()}
      />
    </>
  );
}
