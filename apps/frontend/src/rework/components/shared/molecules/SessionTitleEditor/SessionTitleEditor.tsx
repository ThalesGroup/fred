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

import { KeyboardEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Dialog } from "@shared/molecules/Dialog/Dialog";

interface SessionTitleEditorProps {
  title: string;
  onCommit: (title: string) => void;
  maxLength?: number;
}

export function SessionTitleEditor({ title, onCommit, maxLength = 120 }: SessionTitleEditorProps) {
  const { t } = useTranslation();
  const placeholder = t("chatbot.sessionTitleEditor.untitled");
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");

  const openDialog = () => {
    setDraft(title);
    setOpen(true);
  };

  const commit = () => {
    const trimmed = draft.trim();
    setOpen(false);
    if (trimmed && trimmed !== title) onCommit(trimmed);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && draft.trim()) {
      e.preventDefault();
      commit();
    }
  };

  return (
    <>
      <IconButton
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "edit" }}
        aria-label={t("chatbot.sessionTitleEditor.editAria", { title: title || placeholder })}
        aria-expanded={open}
        onClick={openDialog}
      />

      <Dialog
        open={open}
        title={t("chatbot.sessionTitleEditor.popupLabel")}
        confirmLabel={t("chatbot.sessionTitleEditor.save")}
        confirmDisabled={!draft.trim()}
        onConfirm={commit}
        onCancel={() => setOpen(false)}
      >
        <TextInput
          value={draft}
          maxLength={maxLength}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label={t("chatbot.sessionTitleEditor.inputAria")}
        />
      </Dialog>
    </>
  );
}
