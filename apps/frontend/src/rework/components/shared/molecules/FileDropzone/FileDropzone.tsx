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

import { useId, useRef, useState } from "react";
import { MaterialIcon as Icon } from "../../atoms/Icon/Icon.tsx";
import styles from "./FileDropzone.module.css";

interface FileDropzoneBaseProps {
  /** `accept` attribute for the file input, e.g. ".json,.csv". */
  accept: string;
  /** Primary hint shown inside the zone. */
  hint: string;
  /** Optional secondary line (limits, formats…). */
  subHint?: string;
  disabled?: boolean;
  /** Error message to display below the zone. */
  error?: string;
}

/** Exactly one handler: a dropzone without one does not type-check. */
type FileDropzoneHandler =
  | {
      /** Single-file mode: called with the first picked/dropped file. */
      onFile: (file: File) => void;
      onFiles?: never;
      multiple?: false;
    }
  | {
      /** Multi-file mode: called once with every picked/dropped file. */
      onFiles: (files: File[]) => void;
      onFile?: never;
      /** Let the browse dialog select several files at once. */
      multiple?: boolean;
    };

export type FileDropzoneProps = FileDropzoneBaseProps & FileDropzoneHandler;

/** Drag-and-drop (or click-to-browse) file selector. Design-tokens only. */
export default function FileDropzone({
  accept,
  hint,
  subHint,
  onFile,
  onFiles,
  multiple = false,
  disabled = false,
  error,
}: FileDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = useId();

  const handleFiles = (list: FileList | null | undefined) => {
    const files = Array.from(list ?? []);
    if (files.length === 0 || disabled) return;
    if (onFiles) onFiles(multiple ? files : files.slice(0, 1));
    else if (onFile) onFile(files[0]);
  };

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.zone}
        data-dragging={dragging}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <Icon type="attach_file" />
        <span className={styles.hint}>{hint}</span>
        {subHint && <span className={styles.subHint}>{subHint}</span>}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          className={styles.input}
          onChange={(e) => {
            const files = e.target.files;
            handleFiles(files);
            // Cleared so picking the same file again (after fixing it) fires change.
            e.target.value = "";
          }}
        />
      </button>
      {error && (
        <span id={errorId} role="alert" className={styles.error}>
          {error}
        </span>
      )}
    </div>
  );
}
