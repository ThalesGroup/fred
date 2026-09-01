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

// `useHasContent` for the html_artifact side-panel launcher: has the OPEN
// conversation produced any artifact? A false answer hides the launcher (a button
// onto an empty pane is noise). v1 is read-only with no list API, so the answer is
// purely the live slice — true when it holds at least one artifact for THIS session.

import { useSelector } from "react-redux";
import { useOpenSessionId } from "../useOpenSessionId";
import { selectHtmlArtifactSessionId, selectHtmlArtifactsById } from "./htmlArtifactSlice";

export function useHasHtmlArtifacts(): boolean {
  const openSessionId = useOpenSessionId();
  const sliceSessionId = useSelector(selectHtmlArtifactSessionId);
  const byId = useSelector(selectHtmlArtifactsById);
  // Only count artifacts belonging to the conversation currently open.
  return !!openSessionId && sliceSessionId === openSessionId && Object.keys(byId).length > 0;
}
