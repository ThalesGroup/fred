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

import { Component, lazy, Suspense } from "react";
import type { ReactNode } from "react";
import type { OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import styles from "./MonacoPane.module.css";

class MonacoErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

const Editor = lazy(() => import("@monaco-editor/react").then((m) => ({ default: m.Editor })));

export interface MonacoPaneProps {
  value?: string;
  defaultValue?: string;
  language?: string;
  height?: string;
  readOnly?: boolean;
  theme?: string;
  onChange?: (value: string | undefined) => void;
  onMount?: OnMount;
  /** Merged on top of defaults. scrollbar sizes are always enforced at 6 px. */
  options?: editor.IStandaloneEditorConstructionOptions;
}

export default function MonacoPane({
  value,
  defaultValue,
  language = "json",
  height = "100%",
  readOnly = true,
  theme = "vs-dark",
  onChange,
  onMount,
  options,
}: MonacoPaneProps) {
  const mergedOptions: editor.IStandaloneEditorConstructionOptions = {
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    fontSize: 12,
    ...options,
    readOnly,
    // always enforce thin scrollbars — matches global 6 px convention
    scrollbar: {
      ...options?.scrollbar,
      verticalScrollbarSize: 6,
      horizontalScrollbarSize: 6,
    },
  };

  const fallbackText = value ?? defaultValue ?? "";

  const fallback = <pre className={styles.fallback}>{fallbackText}</pre>;

  return (
    <MonacoErrorBoundary fallback={fallback}>
      <Suspense fallback={fallback}>
        <Editor
          height={height}
          language={language}
          value={value}
          defaultValue={defaultValue}
          theme={theme}
          onChange={onChange}
          onMount={onMount}
          options={mergedOptions}
        />
      </Suspense>
    </MonacoErrorBoundary>
  );
}
