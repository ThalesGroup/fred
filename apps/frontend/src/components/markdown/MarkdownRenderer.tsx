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

import CheckIcon from "@mui/icons-material/Check";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
// import DownloadIcon from "@mui/icons-material/Download"; // REMOVED: Mermaid Download
import { Box, IconButton, Typography, useTheme } from "@mui/material";
import "katex/dist/katex.min.css";
import React, { ComponentPropsWithoutRef, createElement, useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { prism, vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkDirective from "remark-directive";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { PluggableList } from "unified";
import { visit } from "unist-util-visit";
import { useLazyDownloadMarkdownMediaBlobQuery } from "../../slices/knowledgeFlow/knowledgeFlowApi.blob";
import { getMarkdownComponents } from "./GetMarkdownComponents";
import Mermaid from "./Mermaid.tsx";

// --- NEW CITATION INTERFACES ---
interface CitationHooks {
  /** Given [n], return a UID (or null if none) */
  getUidForNumber: (n: number) => string | null;
  /** Hover sync to Sources; pass null on leave */
  onHover?: (uid: string | null) => void;
  /** Click to open/select; optional */
  onClick?: (uid: string | null) => void;
}

export interface MarkdownRendererProps {
  content: string;
  size?: "small" | "medium" | "large";
  enableEmojiSubstitution?: boolean;
  remarkPlugins?: PluggableList;
  components?: Components;
  /** Optional citation behavior; if omitted, renderer ignores [n] */
  citations?: CitationHooks; // <-- ADDED PROP
  /** If provided, relative media paths like media/image.png will be resolved against this document */
  documentUidForMedia?: string;
}

const MARKDOWN_MEDIA_PATH_REGEX = /\/knowledge-flow\/v1\/markdown\/([^/]+)\/media\/([^/?#]+)/;

type MediaInfo = {
  documentUid: string;
  mediaId: string;
  fallbackSrc: string;
};

// Try to pull document/media ids out of the markdown image src so we can fetch with auth.
const extractMediaInfo = (src?: string, fallbackDocumentUid?: string): MediaInfo | null => {
  if (!src) return null;
  // External absolute URLs (e.g. presigned MinIO URLs) are used as-is — skip pattern matching.
  try {
    const parsed = new URL(src);
    if (parsed.origin !== window.location.origin) return null;
  } catch {
    // Not an absolute URL — continue with relative path matching below.
  }
  // Prefer the URL pathname if src is absolute; otherwise keep the raw string to test patterns.
  let path = src;
  try {
    path = new URL(src, window.location.origin).pathname;
  } catch {
    // Ignore parsing errors for relative paths.
  }

  const match = MARKDOWN_MEDIA_PATH_REGEX.exec(path);
  if (match) {
    return {
      documentUid: match[1],
      mediaId: match[2],
      fallbackSrc: src,
    };
  }

  const relativeMedia = path.match(/(?:^|\/)media\/([^/]+)$/);
  if (relativeMedia && fallbackDocumentUid) {
    const mediaId = relativeMedia[1];
    const fallbackSrc = `/knowledge-flow/v1/markdown/${fallbackDocumentUid}/media/${mediaId}`;
    return { documentUid: fallbackDocumentUid, mediaId, fallbackSrc };
  }

  return null;
};

type AuthenticatedImageProps = ComponentPropsWithoutRef<"img"> & {
  documentUidForMedia?: string;
};

const AuthenticatedMarkdownImage: React.FC<AuthenticatedImageProps> = ({ documentUidForMedia, src, ...rest }) => {
  const [resolvedSrc, setResolvedSrc] = useState<string | undefined>(() =>
    src?.startsWith("data:") ? src : undefined,
  );
  const [fetchMedia] = useLazyDownloadMarkdownMediaBlobQuery();

  useEffect(() => {
    // Data URLs are already self-contained.
    if (!src || src.startsWith("data:")) {
      setResolvedSrc(src);
      return;
    }

    const mediaInfo = extractMediaInfo(src, documentUidForMedia);
    if (!mediaInfo) {
      setResolvedSrc(src);
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;

    const request = fetchMedia({ documentUid: mediaInfo.documentUid, mediaId: mediaInfo.mediaId });

    request
      .unwrap()
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setResolvedSrc(objectUrl);
      })
      .catch((err) => {
        if (cancelled) return;
        console.warn("Failed to fetch protected markdown media", err);
        setResolvedSrc(mediaInfo.fallbackSrc);
      });

    return () => {
      cancelled = true;
      request.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [documentUidForMedia, fetchMedia, src]);

  return <img src={resolvedSrc} {...rest} loading="lazy" />;
};
// ... [replaceStageDirectionsWithEmoji remains the same]
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

/* -------------------------------------------------------------------------- */
/* CODE BLOCK CONTAINER FOR COPY/DOWNLOAD FUNCTIONALITY (Mermaid Removed)     */
/* -------------------------------------------------------------------------- */

interface CodeBlockContainerProps {
  children: React.ReactNode;
  codeContent: string;
  language?: string; // For display and file extension
  // isMermaid: boolean; // REMOVED: Mermaid Prop
}

const CodeBlockContainer: React.FC<CodeBlockContainerProps> = ({
  children,
  codeContent,
  language /* , isMermaid */,
}) => {
  const theme = useTheme();
  const [copied, setCopied] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null); // Ref for potential future use (or remove if not needed)

  const handleCopy = () => {
    navigator.clipboard.writeText(codeContent).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  // const handleDownload = () => {
  //   // REMOVED: All Mermaid Download Logic
  //   if (!containerRef.current || !isMermaid) return;
  //   // ... (SVG serialization and download)
  // };

  const backgroundColor = theme.palette.mode === "dark" ? theme.palette.grey[900] : theme.palette.grey[200];
  const headerColor = theme.palette.mode === "dark" ? theme.palette.grey[700] : theme.palette.grey[300];

  return (
    <Box
      ref={containerRef}
      sx={{
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 1,
        overflow: "hidden",
        mb: 2, // Margin bottom for separation
      }}
    >
      {/* Toolbar Header */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          p: 1,
          backgroundColor: headerColor,
        }}
      >
        {/* Language/Type Display */}
        <Typography
          variant="caption"
          sx={{
            textTransform: "uppercase",
            fontWeight: "bold",
            color: theme.palette.text.secondary,
          }}
        >
          {/* {isMermaid ? "Diagram (Mermaid)" : language || "Code"} */} {/* Simplified to: */}
          {language || "Code"}
        </Typography>

        {/* Action Buttons */}
        <Box>
          {/* Copy Button (Now always present for code blocks) */}
          <IconButton size="small" onClick={handleCopy} color={copied ? "success" : "default"}>
            {/* Conditional Icon Rendering */}
            {copied ? (
              <CheckIcon fontSize="inherit" /> // Show Checkmark on success
            ) : (
              <ContentCopyIcon fontSize="inherit" /> // Show Copy icon by default
            )}
          </IconButton>

          {/* Download Button for Diagrams (REMOVED) */}
          {/* {isMermaid && (
            <SimpleTooltip title="Download Diagram (SVG)" placement="top">
              <IconButton size="small" onClick={handleDownload} color="default">
                <DownloadIcon fontSize="inherit" />
              </IconButton>
            </SimpleTooltip>
          )} */}
        </Box>
      </Box>

      {/* Content Area */}
      {/* Mermaid content area had different padding (0). Now standardized: */}
      <Box sx={{ p: 0, backgroundColor: backgroundColor }}>{children}</Box>
    </Box>
  );
};

// ... [remarkDetailsContainers remains the same]
function remarkDetailsContainers() {
  return (tree: any) => {
    visit(tree, (node: any, idx: number | null, parent: any) => {
      if (!parent) return;

      // remark-directive marks this as: containerDirective with name 'details'
      if (node.type === "containerDirective" && node.name === "details") {
        // Extract summary: prefer explicit label ":::details[Summary]" if present,
        // else use the first paragraph's text
        let summaryText = "";
        if (node.label) {
          summaryText = String(node.label);
        } else if (node.children?.length && node.children[0]?.type === "paragraph") {
          const firstPara = node.children[0];
          summaryText = firstPara.children?.map((c: any) => c.value || "").join("") || "Details";
          // remove that paragraph from body
          node.children = node.children.slice(1);
        } else {
          summaryText = "Details";
        }

        // Build <details><summary>…</summary>…</details>
        const detailsHast = {
          type: "containerDirective",
          data: { hName: "details" },
          children: [
            {
              type: "textDirective",
              data: { hName: "summary" },
              children: [{ type: "text", value: summaryText }],
            },
            ...node.children,
          ],
        };

        parent.children[idx!] = detailsHast;
      }
    });
  };
}

/* -------------------------------------------------------------------------- */
/* MERMAID LOGIC (REMOVED)                                                    */
/* -------------------------------------------------------------------------- */

// const MermaidDiagram: React.FC<{ value: string }> = ({ value }) => {
//   // REMOVED: Entire MermaidDiagram component
// };

/* -------------------------------------------------------------------------- */
/* HIGHLIGHTER THEME PICKER (No change needed here)                            */
/* -------------------------------------------------------------------------- */

const useCodeHighlightStyle = () => {
  const theme = useTheme();
  const isDarkMode = theme.palette.mode === "dark";
  return isDarkMode ? vscDarkPlus : prism;
};

// Custom Code Component (UPDATED to remove Mermaid logic)
const CustomCodeComponent: Components["code"] = ({ className, children, ...props }) => {
  const codeStyle = useCodeHighlightStyle();
  const match = /language-(\w+)/.exec(className || "");
  const lang = match?.[1];
  const codeContent = String(children);

  // 1. Handle Mermaid Diagrams
  if (lang === "mermaid") {
    const diagramCode = codeContent.trim();
    return (
      <CodeBlockContainer codeContent={diagramCode} language="mermaid">
        <Mermaid code={diagramCode} />
      </CodeBlockContainer>
    );
  }

  // 2. Handle Fenced Code Blocks (Syntax Highlighting)
  if (lang) {
    // The rendered element (SyntaxHighlighter) needs to be nested inside the container
    const highlighter = (
      <SyntaxHighlighter
        language={lang}
        style={codeStyle}
        PreTag="pre"
        // Ensure PreTag gets NO padding/margin from react-syntax-highlighter
        customStyle={{ margin: 0, padding: 16 }}
        {...props}
      >
        {codeContent.trim()} {/* Trim content passed to highlighter */}
      </SyntaxHighlighter>
    );

    // Wrap the Highlighter in the container
    return (
      <CodeBlockContainer codeContent={codeContent} language={lang}>
        {highlighter}
      </CodeBlockContainer>
    );
  }

  // 3. Fallback for Inline Code (Do NOT wrap inline code in the container)
  return createElement("code", { className, ...props }, children);
};

/* -------------------------------------------------------------------------- */
/* CITATION REHYPE PLUGIN                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Rehype plugin: transform [n] text patterns into <sup class="fred-cite" data-n="n"> HAST
 * elements before sanitization.  Running inside the rehype pipeline means citations are
 * native React elements that React reconciles properly — no post-render DOM mutation, no
 * streaming flicker.  Text nodes inside code/pre/kbd/samp are skipped.
 */
function rehypeCitations() {
  const SKIP_TAGS = new Set(["code", "pre", "kbd", "samp"]);
  const CITATION_RE = /\[(\d+)\]/g;

  return (tree: any) => {
    visit(tree, "text", (node: any, index: number | null, parent: any) => {
      if (index == null || !parent) return;
      if (parent.type === "element" && SKIP_TAGS.has(parent.tagName)) return;

      CITATION_RE.lastIndex = 0;
      if (!CITATION_RE.test(node.value)) return;
      CITATION_RE.lastIndex = 0;

      const parts: any[] = [];
      let last = 0;
      let m: RegExpExecArray | null;
      while ((m = CITATION_RE.exec(node.value)) !== null) {
        if (m.index > last) parts.push({ type: "text", value: node.value.slice(last, m.index) });
        parts.push({
          type: "element",
          tagName: "sup",
          properties: { className: ["fred-cite"], "data-n": m[1] },
          children: [{ type: "text", value: `[${m[1]}]` }],
        });
        last = m.index + m[0].length;
      }
      if (last < node.value.length) parts.push({ type: "text", value: node.value.slice(last) });

      if (parts.length > 1) {
        parent.children.splice(index, 1, ...parts);
      }
    });
  };
}

/* -------------------------------------------------------------------------- */
/* MARKDOWN RENDERER CORE (Mermaid Initialization Removed)                     */
/* -------------------------------------------------------------------------- */

export default function MarkdownRenderer({
  content,
  size = "medium",
  enableEmojiSubstitution = false,
  remarkPlugins = [],
  citations,
  documentUidForMedia,
  ...props
}: MarkdownRendererProps) {
  const theme = useTheme();

  const finalContent = enableEmojiSubstitution
    ? replaceStageDirectionsWithEmoji(content || "")
    : content || "No markdown content provided.";

  const baseComponents = getMarkdownComponents({
    theme,
    size,
    enableEmojiFix: true,
  });

  const finalComponents: Components = {
    ...baseComponents,
    code: CustomCodeComponent,
    img: ({ node, ...imageProps }) => (
      <AuthenticatedMarkdownImage {...imageProps} documentUidForMedia={documentUidForMedia} />
    ),
    sup: ({ node, children, ...supProps }) => {
      const n = (supProps as any)["data-n"] !== undefined ? Number((supProps as any)["data-n"]) : undefined;
      if (n !== undefined && citations) {
        const uid = citations.getUidForNumber(n);
        return (
          <sup
            className="fred-cite"
            data-n={String(n)}
            onMouseEnter={() => citations.onHover?.(uid)}
            onMouseLeave={() => citations.onHover?.(null)}
            onClick={() => citations.onClick?.(uid)}
            role="button"
            tabIndex={0}
            aria-label={`Citation ${n}`}
            onKeyDown={(e: React.KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                citations.onClick?.(uid);
              }
            }}
          >
            {children}
          </sup>
        );
      }
      return <sup {...(supProps as any)}>{children}</sup>;
    },
    ...(props.components || {}),
  };

  const sanitizeSchema = {
    ...defaultSchema,
    tagNames: [...(defaultSchema.tagNames || []), "details", "summary"],
    attributes: {
      ...(defaultSchema.attributes || {}),
      details: ["open"],
      sup: [...(defaultSchema.attributes?.sup ?? []), "data-n"],
    },
  };

  /* --------------------------------------------------------- */
  /* Mermaid theming (REMOVED: Initialization useEffect)       */
  /* --------------------------------------------------------- */
  // useEffect(() => {
  //   mermaid.initialize({
  //     startOnLoad: false,
  //     securityLevel: "loose",
  //     theme: theme.palette.mode === "dark" ? "dark" : "default",
  //     themeVariables: {
  //       primaryColor: theme.palette.primary.main,
  //       primaryTextColor: theme.palette.getContrastText(theme.palette.primary.main),
  //       lineColor: theme.palette.divider,
  //       background: theme.palette.background.paper,
  //       noteBkgColor: theme.palette.background.paper,
  //       noteTextColor: theme.palette.text.primary,
  //     },
  //     loader: { loadAll: true },
  //   } as any);
  // }, [theme.palette.mode, theme.palette.primary.main, theme.palette.divider, theme.palette.background.paper]);

  return (
    <Box
      sx={{
        "& .fred-cite": {
          position: "relative",
          top: "-0.2em",
          marginLeft: "2px",
          marginRight: "2px",
          padding: "0 4px",
          borderRadius: "10px",
          fontSize: "0.85em",
          userSelect: "none",
          cursor: "pointer",
          background: theme.palette.action.hover,
          border: `1px solid ${theme.palette.divider}`,
          transition: "background 0.2s",
        },
        "& .fred-cite--hover": {
          background: theme.palette.action.selected,
          borderColor: theme.palette.action.active,
        },
      }}
    >
      <ReactMarkdown
        skipHtml={false}
        components={finalComponents}
        remarkPlugins={[
          remarkGfm,
          remarkMath,
          remarkDirective,
          remarkDetailsContainers,
          ...remarkPlugins,
        ]}
        rehypePlugins={[rehypeRaw, rehypeCitations, [rehypeSanitize, sanitizeSchema], rehypeKatex]}
      >
        {finalContent}
      </ReactMarkdown>
    </Box>
  );
}
