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

import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark, oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useIsDark } from "../../../../core/hooks/useIsDark";
import styles from "./CodeBlock.module.css";

interface CodeBlockProps {
  code: string;
  language?: string;
  inline?: boolean;
}

export function CodeBlock({ code, language, inline = false }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const isDark = useIsDark();

  if (inline) {
    return <code className={styles.inline}>{code}</code>;
  }

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className={styles.block}>
      <div className={styles.header}>
        <span className={styles.lang}>{language ?? "plaintext"}</span>
        <button className={styles.copy} onClick={handleCopy} aria-label="Copy code">
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language ?? "plaintext"}
        style={isDark ? oneDark : oneLight}
        customStyle={{
          margin: 0,
          padding: "var(--spacing-m, 16px)",
          background: "var(--surface-container-lowest)",
          fontSize: "0.875rem",
          lineHeight: "1.6",
          fontFamily: '"Geist Mono", "Fira Code", ui-monospace, monospace',
          overflowX: "auto",
          borderRadius: 0,
        }}
        codeTagProps={{ style: { fontFamily: "inherit" } }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
