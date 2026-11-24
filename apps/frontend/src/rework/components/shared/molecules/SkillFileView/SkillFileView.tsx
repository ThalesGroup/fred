// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState, type ReactNode } from "react";
import Button from "@shared/atoms/Button/Button";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import styles from "./SkillFileView.module.css";

/** The library and catalogue use the same file selection and safe Markdown reader. */
export function SkillFileView({
  files,
  path,
  onPathChange,
  children,
}: {
  files: Record<string, string>;
  path?: string;
  onPathChange?: (path: string) => void;
  children?: ReactNode;
}) {
  const [selected, setSelected] = useState("SKILL.md");
  const current = path ?? selected;
  return (
    <>
      <div className={styles.files}>
        {Object.keys(files).map((file) => (
          <Button
            size="small"
            key={file}
            variant="text"
            color="primary"
            onClick={() => (onPathChange ?? setSelected)(file)}
          >
            {file}
          </Button>
        ))}
      </div>
      {children ?? <MarkdownRenderer text={files[current] ?? ""} fullWidth localLinksAsText diagramsAsCode />}
    </>
  );
}
