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

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { ConversationFilePart } from "../../../slices/runtime/runtimeOpenApi";

interface ConversationFileState {
  sessions: Record<
    string,
    {
      files: Record<string, ConversationFilePart>;
      selectedPath: string | null;
      revision: number;
      refreshRevision: number;
    }
  >;
  routes: Record<string, string>;
}
// Session IDs are data, including names that collide with object prototype keys.
const sessionKey = (sessionId: string) => JSON.stringify(sessionId);
const initialState: ConversationFileState = { sessions: {}, routes: {} };
export const FILE_PANEL_KEY = "runtime:conversation-files";
export const conversationFileSlice = createSlice({
  name: "conversationFiles",
  initialState,
  reducers: {
    rememberConversationFile(state, { payload }: PayloadAction<ConversationFilePart>) {
      const session = (state.sessions[sessionKey(payload.session_id)] ??= {
        files: {},
        selectedPath: null,
        revision: 0,
        refreshRevision: 0,
      });
      session.files[payload.path] = payload;
    },
    openConversationFile(state, { payload }: PayloadAction<ConversationFilePart>) {
      const session = (state.sessions[sessionKey(payload.session_id)] ??= {
        files: {},
        selectedPath: null,
        revision: 0,
        refreshRevision: 0,
      });
      session.files[payload.path] = payload;
      session.selectedPath = payload.path;
      session.revision += 1;
    },
    refreshConversationFiles(state, { payload }: PayloadAction<string>) {
      const session = state.sessions[sessionKey(payload)];
      if (session) session.refreshRevision += 1;
    },
    setConversationFileRoute(state, { payload }: PayloadAction<{ sessionId: string; baseUrl: string | null }>) {
      if (payload.baseUrl) state.routes[sessionKey(payload.sessionId)] = payload.baseUrl;
      else delete state.routes[sessionKey(payload.sessionId)];
    },
  },
});
export const { rememberConversationFile, openConversationFile, setConversationFileRoute, refreshConversationFiles } =
  conversationFileSlice.actions;
export type ConversationFileRootState = { conversationFiles: ConversationFileState };

export const selectConversationFileSession = (state: ConversationFileRootState, sessionId: string) =>
  state.conversationFiles.sessions[sessionKey(sessionId)];
export const selectConversationFileRoute = (state: ConversationFileRootState, sessionId: string) =>
  state.conversationFiles.routes[sessionKey(sessionId)];
