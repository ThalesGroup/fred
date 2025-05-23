// Copyright Thales 2025
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

import { useTheme } from "@mui/material";
import Mermaid from "../markdown/Mermaid.tsx";
import ReactMarkdown from "react-markdown";

function replaceStageDirectionsWithEmoji(text: string): string {
  return text
    .replace(/\badjusts glasses\b/gi, "🤓")
    .replace(/\bsmiles\b/gi, "😶")
    .replace(/\bshrugs\b/gi, "🤷")
    .replace(/\bnods\b/gi, "👍")
    .replace(/\blaughs\b/gi, "😂")
    .replace(/\bsighs\b/gi, "😮‍💨")
    .replace(/\bgrins\b/gi, "😁")
    .replace(/\bwinks\b/gi, "😉")
    .replace(/\bclears throat\b/gi, "😶‍🌫️");
}

export default function MarkdownRenderer({
  content,
}: {
  content: string;
}) {
  const theme = useTheme();

  const handleMermaid = ({
    node,
    inline,
    className,
    children,
    ...props
  }) => {
    const match = /language-mermaid/.exec(className || '');
    if (match && children) {
      return <Mermaid code={String(children).replace(/\n$/, '')} />;
    }
    return (
      <code style={{ ...theme.typography.markdown.code }} {...props}>
        {children}
      </code>
    );
  };

  const components = {
    h1: ({ node, ...props }) => (
      <h1 style={{ ...theme.typography.markdown.h1 }} {...props} />
    ),
    h2: ({ node, ...props }) => (
      <h2 style={{ ...theme.typography.markdown.h2 }} {...props} />
    ),
    h3: ({ node, ...props }) => (
      <h3 style={{ ...theme.typography.markdown.h3 }} {...props} />
    ),
    h4: ({ node, ...props }) => (
      <h4 style={{ ...theme.typography.markdown.h4 }} {...props} />
    ),
    p: ({ node, ...props }) => (
      <p
        style={{
          fontStyle: 'normal', // 👈 Ensures emojis don't inherit italics
          ...theme.typography.markdown.p,
        }}
        {...props}
      />
    ),

    /* em: ({ node, children, ...props }) => {
        const onlyEmoji = typeof children[0] === "string" && /^[\p{Emoji}\s]+$/u.test(children[0]);
        return (
          <em
            style={{
              fontStyle: onlyEmoji ? "normal" : "italic",
            }}
            {...props}
          />
        );
    }, */
      
    em: ({ node, ...props }) => (
      <em
        style={{
          fontStyle: 'normal', // 👈 Optional: disables italics inside emphasis
        }}
        {...props}
      />
    ),
    a: ({ node, ...props }) => (
      <a style={{ ...theme.typography.markdown.a }} {...props} />
    ),
    ul: ({ node, ...props }) => (
      <ul style={{ ...theme.typography.markdown.ul }} {...props} />
    ),
    li: ({ node, ...props }) => (
      <li style={{ ...theme.typography.markdown.li }} {...props} />
    ),
    code: ({ node, inline, className, children, ...props }) =>
      handleMermaid({
        node,
        inline,
        className,
        children,
        ...props,
      }),
  };

  const formattedContent = replaceStageDirectionsWithEmoji(content || "");

  return (
    <ReactMarkdown components={components}>
      {formattedContent}
    </ReactMarkdown>
  );
}
