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

import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";

// Every runtime pause holds the composer until its card is answered, except an
// interrupted run, whose "Later" choice exists to keep chatting.
export function hitlHoldsComposer(event: RuntimeAwaitingHumanEvent | null | undefined, sessionId: string | null) {
  return !!event && event.session_id === sessionId && event.payload.stage !== "execution_interrupted";
}
