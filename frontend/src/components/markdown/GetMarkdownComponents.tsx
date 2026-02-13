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

import Mermaid from "./Mermaid.tsx";
import { alpha, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Theme } from "@mui/material";

interface GetMarkdownComponentsOptions {
  theme: Theme;
  size: "small" | "medium" | "large";
  enableEmojiFix?: boolean;
}

export function getMarkdownComponents({ theme, size, enableEmojiFix = true }: GetMarkdownComponentsOptions) {
  const baseStyle = (style: any) => (size === "small" ? { ...style, fontSize: "0.85rem" } : style);

  return {
    h1: ({ node, ...props }) => <h1 style={baseStyle(theme.typography.markdown.h1)} {...props} />,
    h2: ({ node, ...props }) => <h2 style={baseStyle(theme.typography.markdown.h2)} {...props} />,
    h3: ({ node, ...props }) => <h3 style={baseStyle(theme.typography.markdown.h3)} {...props} />,
    h4: ({ node, ...props }) => <h4 style={baseStyle(theme.typography.markdown.h4)} {...props} />,
    p: ({ node, ...props }) => (
      <p
        style={{
          fontStyle: enableEmojiFix ? "normal" : undefined,
          ...baseStyle(theme.typography.markdown.p),
        }}
        {...props}
      />
    ),
    em: ({ node, ...props }) => (
      <em
        style={{
          fontStyle: enableEmojiFix ? "normal" : undefined,
        }}
        {...props}
      />
    ),
    a: ({ node, ...props }) => <a style={baseStyle(theme.typography.markdown.a)} target="_blank" rel="noopener noreferrer" {...props} />,
    ul: ({ node, ...props }) => <ul style={baseStyle(theme.typography.markdown.ul)} {...props} />,
    li: ({ node, ...props }) => <li style={baseStyle(theme.typography.markdown.li)} {...props} />,
    code: ({ node, inline, className, children, ...props }) => {
      const isMermaid = /language-mermaid/.test(className || "");
      if (isMermaid && children) {
        return <Mermaid code={String(children).replace(/\n$/, "")} />;
      }
      return (
        <code style={baseStyle(theme.typography.markdown.code)} {...props}>
          {children}
        </code>
      );
    },

    // Markdown tables rendered with MUI Table components
    table: ({ node, ...props }) => (
      <TableContainer
        component={Paper}
        sx={{
          marginTop: theme.spacing(1),
          overflowX: "auto",
        }}
      >
        <Table
          size={size === "small" ? "small" : "medium"}
          sx={{
            borderCollapse: "collapse",
            minWidth: "100%",
            "& td, & th": {
              border: `1px solid ${theme.palette.divider}`,
              padding: theme.spacing(1),
              textAlign: "left",
            },
          }}
          {...props}
        />
      </TableContainer>
    ),
    thead: ({ node, ...props }) => (
      <TableHead
        sx={{
          backgroundColor:
            theme.palette.mode === "dark"
              ? alpha(theme.palette.primary.main, 0.2)
              : alpha(theme.palette.primary.main, 0.1),
        }}
        {...props}
      />
    ),
    tbody: ({ node, ...props }) => <TableBody {...props} />,
    tr: ({ node, ...props }) => <TableRow {...props} />,
    th: ({ node, ...props }) => (
      <TableCell
        component="th"
        sx={{
          fontWeight: theme.typography.fontWeightBold,
          color: theme.palette.text.primary,
          border: `1px solid ${theme.palette.divider}`,
          padding: theme.spacing(1),
          textAlign: "left",
        }}
        {...props}
      />
    ),
    td: ({ node, ...props }) => (
      <TableCell
        sx={{
          color: theme.palette.text.primary,
          border: `1px solid ${theme.palette.divider}`,
          padding: theme.spacing(1),
          textAlign: "left",
        }}
        {...props}
      />
    ),
  };
}
