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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./FileDropzone.module.css";

interface FileDropzoneProps {
  /** `accept` attribute for the file input, e.g. ".json,.csv". */
  accept: string;
  /** Primary hint shown inside the zone. */
  hint: string;
  /** Optional secondary line (limits, formats…). */
  subHint?: string;
  onFile: (file: File) => void;
  /** Error message to display below the zone. */
  error?: string;
}

/** Drag-and-drop (or click-to-browse) file selector. Design-tokens only. */
export default function FileDropzone({ accept, hint, subHint, onFile, error }: FileDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.zone}
        data-dragging={dragging}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) onFile(file);
        }}
      >
        <Icon category="outlined" type="attach_file" />
        <span className={styles.hint}>{hint}</span>
        {subHint && <span className={styles.subHint}>{subHint}</span>}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className={styles.input}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onFile(file);
          }}
        />
      </button>
      {error && <span className={styles.error}>{error}</span>}
    </div>
  );
}
