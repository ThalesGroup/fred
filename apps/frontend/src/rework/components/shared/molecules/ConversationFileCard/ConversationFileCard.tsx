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

import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { useMountSessionId } from "@rework/features/capabilities/useOpenSessionId";
import { requestSidePanelOpen } from "@rework/features/capabilities/sidePanelOpenRequestSlice";
import type { UiPartRendererProps } from "@rework/features/capabilities/types";
import type { ConversationFilePart } from "../../../../../slices/runtime/runtimeOpenApi";
import {
  openConversationFile,
  rememberConversationFile,
} from "@rework/features/conversationFiles/conversationFileSlice";

export function ConversationFileCard({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const sessionId = useMountSessionId();
  const file = part as unknown as ConversationFilePart;
  const valid = file.session_id === sessionId && typeof file.path === "string" && file.path.startsWith("/");
  useEffect(() => {
    if (valid) dispatch(rememberConversationFile(file));
  }, [dispatch, file, valid]);
  if (!valid) return null;
  return (
    <Button
      color="primary"
      variant="text"
      size="small"
      onClick={() => {
        dispatch(openConversationFile(file));
        dispatch(requestSidePanelOpen({ capabilityId: "runtime", widget: "conversation-files" }));
      }}
      aria-label={t("conversationFiles.openPath", { path: file.path })}
    >
      {t("conversationFiles.open")} {file.path}
    </Button>
  );
}
