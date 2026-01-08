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
import Mermaid from "./Mermaid.tsx";
import { createElement, useEffect, useRef, useState } from "react";
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

type AuthenticatedImageProps = JSX.IntrinsicElements["img"] & { documentUidForMedia?: string };

const AuthenticatedMarkdownImage: React.FC<AuthenticatedImageProps> = ({
  documentUidForMedia,
  src,
  ...rest
}) => {
  const [resolvedSrc, setResolvedSrc] = useState<string | undefined>(() => (src?.startsWith("data:") ? src : undefined));
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
            <Tooltip title="Download Diagram (SVG)" placement="top">
              <IconButton size="small" onClick={handleDownload} color="default">
                <DownloadIcon fontSize="inherit" />
              </IconButton>
            </Tooltip>
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
/* NEW: CITATION HOOKS (Logic moved from your old renderer)                    */
/* -------------------------------------------------------------------------- */

/** Walk all text nodes under root, excluding code/citations, to inject sup tags */
function forEachTextNode(root: HTMLElement, excludeSelector: string, fn: (textNode: Text) => void) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      // Exclude nodes inside pre, code, etc.
      // NOTE: Removed '.mermaid' from the exclusion selector
      if (parent.closest(excludeSelector)) return NodeFilter.FILTER_REJECT;
      // Only process text nodes that contain a potential citation pattern
      if (!node.nodeValue || !node.nodeValue.match(/\[\d+\]/)) {
        return NodeFilter.FILTER_SKIP;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let node: Node | null;
  while ((node = walker.nextNode())) fn(node as Text);
}

/** Replace [n] in a text node with <sup class="fred-cite" data-n="n">[n]</sup> */
function injectCitationSup(textNode: Text) {
  const parent = textNode.parentNode as HTMLElement;
  const txt = textNode.nodeValue || "";
  // Split by citation pattern, keeping the delimiters
  const parts = txt.split(/(\[\d+\])/g);
  if (parts.length === 1) return;

  const frag = document.createDocumentFragment();
  for (const part of parts) {
    const m = part.match(/^\[(\d+)\]$/);
    if (!m) {
      frag.appendChild(document.createTextNode(part));
      continue;
    }
    const n = Number(m[1]);
    const sup = document.createElement("sup");
    sup.className = "fred-cite";
    sup.setAttribute("data-n", String(n));
    sup.textContent = `[${n}]`;
    frag.appendChild(sup);
  }
  // Replace the original text node with the new fragment
  parent.replaceChild(frag, textNode);
}

const useCitationEnrichment = (containerRef: React.RefObject<HTMLElement>, citations?: CitationHooks) => {
  useEffect(() => {
    if (!containerRef.current || !citations) return;

    const container = containerRef.current;

    // 1) Inject <sup.fred-cite> for every [n] in text nodes (exclude code-like)
    // Removed '.mermaid' from the exclude selector
    forEachTextNode(container, "pre, code, kbd, samp, .fred-cite", injectCitationSup);

    // 2) Attach handlers and ARIA to the newly created <sup> elements
    const nodes = Array.from(container.querySelectorAll<HTMLElement>("sup.fred-cite"));

    const onEnter = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      const n = Number(el.getAttribute("data-n") || "0");
      const uid = citations.getUidForNumber(n);
      el.classList.add("fred-cite--hover");
      citations.onHover?.(uid);
    };
    const onLeave = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      el.classList.remove("fred-cite--hover");
      citations.onHover?.(null);
    };
    const onClick = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      const n = Number(el.getAttribute("data-n") || "0");
      const uid = citations.getUidForNumber(n);
      citations.onClick?.(uid);
    };
    const onKeydown = (ke: KeyboardEvent) => {
      if (ke.key === "Enter" || ke.key === " ") {
        ke.preventDefault();
        onClick(ke as unknown as Event);
      }
    };

    nodes.forEach((el) => {
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-label", `Citation ${el.getAttribute("data-n")}`);
      el.addEventListener("mouseenter", onEnter);
      el.addEventListener("mouseleave", onLeave);
      el.addEventListener("click", onClick);
      el.addEventListener("keydown", onKeydown);
    });

    // Cleanup
    return () => {
      nodes.forEach((el) => {
        el.removeEventListener("mouseenter", onEnter);
        el.removeEventListener("mouseleave", onLeave);
        el.removeEventListener("click", onClick);
        el.removeEventListener("keydown", onKeydown);
        // Note: We don't remove the <sup> elements themselves here,
        // as they will be re-rendered and replaced by the next ReactMarkdown run.
      });
    };
  }, [containerRef, citations]);
};

/* -------------------------------------------------------------------------- */
/* MARKDOWN RENDERER CORE (Mermaid Initialization Removed)                     */
/* -------------------------------------------------------------------------- */

export default function MarkdownRenderer({
  content,
  size = "medium",
  enableEmojiSubstitution = false,
  remarkPlugins = [],
  citations, // <-- DESTUCTURE CITATIONS PROP
  documentUidForMedia,
  ...props
}: MarkdownRendererProps) {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null); // Ref to hold the root DOM element

  // Execute the custom citation logic hook after rendering
  useCitationEnrichment(containerRef, citations); // <-- CALL THE NEW HOOK HERE

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
    ...(props.components || {}),
  };

  const sanitizeSchema = {
    ...defaultSchema,
    tagNames: [...(defaultSchema.tagNames || []), "details", "summary"],
    attributes: {
      ...(defaultSchema.attributes || {}),
      details: ["open"], // allow the boolean 'open' attribute
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
      ref={containerRef}
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
          remarkDirective, // 👈 must come before our details transformer
          remarkDetailsContainers, // 👈 turns :::details into real <details>
          ...remarkPlugins,
        ]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeKatex]}
      >
        {finalContent}
      </ReactMarkdown>
    </Box>
  );
}
