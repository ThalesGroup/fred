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

import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/** Router state that opens a new conversation with a question already asked. */
export interface InitialPromptState {
  initialPrompt: string;
}

export const initialPromptState = (text: string): InitialPromptState => ({ initialPrompt: text });

function readInitialPrompt(state: unknown): string | null {
  const text = (state as Partial<InitialPromptState> | null)?.initialPrompt;
  return typeof text === "string" && text.trim() ? text.trim() : null;
}

interface UseInitialPromptOptions {
  input: string;
  setInput: (text: string) => void;
  send: () => void;
  /** The composer accepts a send now (agent known, nothing loading or pending). */
  ready: boolean;
}

// A chat reset (strict-mode double effects, a late re-entry) may wipe the
// copied text before it is sent: it is copied again, a bounded number of times.
const MAX_COPIES = 3;

/**
 * A question asked from the home page: shown in the composer, then sent once.
 * It travels in router state, not the URL, and the state is cleared at once so
 * a reload or a back navigation never sends it again.
 */
export function useInitialPrompt({ input, setInput, send, ready }: UseInitialPromptOptions) {
  const location = useLocation();
  const navigate = useNavigate();
  // A ref, so double effects cannot send twice.
  const pending = useRef<{ text: string; step: "copy" | "send" | "done"; copies: number } | null>(null);
  if (pending.current === null) {
    const text = readInitialPrompt(location.state);
    pending.current = text ? { text, step: "copy", copies: 0 } : { text: "", step: "done", copies: 0 };
  }
  const hasRouterPrompt = readInitialPrompt(location.state) !== null;

  useEffect(() => {
    if (!hasRouterPrompt) return;
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null });
  }, [hasRouterPrompt, location.pathname, location.search, navigate]);

  useEffect(() => {
    const current = pending.current;
    if (!current || current.step === "done" || !ready) return;
    if (current.step === "send" && input === current.text) {
      current.step = "done";
      send();
      return;
    }
    // Something else typed by the person wins over the home question.
    if (input !== "" && input !== current.text) {
      current.step = "done";
      return;
    }
    if (current.copies >= MAX_COPIES) {
      current.step = "done";
      return;
    }
    current.copies += 1;
    current.step = "send";
    setInput(current.text);
  }, [input, ready, send, setInput]);
}
