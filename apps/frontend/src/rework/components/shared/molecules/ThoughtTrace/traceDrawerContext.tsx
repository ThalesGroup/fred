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

import { createContext, useContext } from "react";
import type { TraceEntry } from "../../../../utils/traceUtils";

/**
 * Lets a deeply-nested {@link TraceEntryRow} open the trace detail panel that is
 * mounted at the page level. The panel must be a sibling of the chat's main
 * column so it can use `layout="push"` and reflow the conversation instead of
 * overlaying it — which is impossible if every row mounts its own drawer.
 *
 * The default `openTrace` is a no-op so rows render safely outside a provider.
 */
export interface TraceDrawerApi {
  openTrace: (entry: TraceEntry) => void;
}

const TraceDrawerContext = createContext<TraceDrawerApi>({ openTrace: () => {} });

export const TraceDrawerProvider = TraceDrawerContext.Provider;

export function useTraceDrawer(): TraceDrawerApi {
  return useContext(TraceDrawerContext);
}
