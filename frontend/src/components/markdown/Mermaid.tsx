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

import React, { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { Box, IconButton, Modal } from "@mui/material";
import ZoomInIcon from "@mui/icons-material/ZoomIn";
import SaveIcon from "@mui/icons-material/Save";
import { alpha, useTheme } from "@mui/material/styles";

interface MermaidProps {
  code: string;
}

interface MermaidRenderCandidate {
  name: string;
  code: string;
}

type PaletteMode = "light" | "dark";

const uniqueCandidates = (candidates: MermaidRenderCandidate[]): MermaidRenderCandidate[] => {
  const seen = new Set<string>();
  return candidates.filter((candidate) => {
    if (!candidate.code.trim()) return false;
    if (seen.has(candidate.code)) return false;
    seen.add(candidate.code);
    return true;
  });
};

const toErrorMessage = (err: unknown): string => {
  if (err instanceof Error && err.message) return err.message;
  try {
    return String(err);
  } catch {
    return "Unknown Mermaid render error";
  }
};

const parseSvgLength = (value: string | null): number | null => {
  if (!value) return null;
  const match = value.trim().match(/^([0-9]*\.?[0-9]+)/);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
};

const replaceOrAppendClassDef = (code: string, className: string, classDefLine: string): string => {
  const re = new RegExp(`^\\s*classDef\\s+${className}\\b.*$`, "m");
  if (re.test(code)) return code.replace(re, classDefLine);
  return `${code.trimEnd()}\n${classDefLine}\n`;
};

const applyLangGraphContrastOverrides = (code: string, paletteMode: PaletteMode): string => {
  // LangGraph draw_mermaid() commonly emits these class defs with pastel fills.
  // In dark UI mode, Mermaid's dark-theme text can become too light on those pale nodes.
  const looksLikeLangGraph =
    code.includes("__start__") &&
    /classDef\s+default\b/.test(code) &&
    /classDef\s+first\b/.test(code) &&
    /classDef\s+last\b/.test(code);

  if (!looksLikeLangGraph) return code;

  const defs =
    paletteMode === "dark"
      ? {
          // Light nodes + dark text for readability in dark-mode UI
          default:
            "classDef default fill:#f8fafc,stroke:#64748b,stroke-width:1.25px,color:#0f172a,line-height:1.2",
          // Start node is transparent in LangGraph style; keep it visible on dark background
          first:
            "classDef first fill-opacity:0,stroke:#cbd5e1,stroke-width:1px,color:#e5e7eb",
          // End node accent with readable dark text
          last: "classDef last fill:#93c5fd,stroke:#2563eb,stroke-width:1.25px,color:#0f172a",
        }
      : {
          default:
            "classDef default fill:#ffffff,stroke:#475569,stroke-width:1.25px,color:#111827,line-height:1.2",
          first:
            "classDef first fill-opacity:0,stroke:#94a3b8,stroke-width:1px,color:#334155",
          last: "classDef last fill:#dbeafe,stroke:#2563eb,stroke-width:1.25px,color:#111827",
        };

  let out = code;
  out = replaceOrAppendClassDef(out, "default", defs.default);
  out = replaceOrAppendClassDef(out, "first", defs.first);
  out = replaceOrAppendClassDef(out, "last", defs.last);
  return out;
};

const cleanupMermaidArtifacts = (diagramId: string) => {
  try {
    const escapedId = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(diagramId) : diagramId;
    const selectors = [
      `#${escapedId}`,
      `[id="${diagramId}"]`,
      // Mermaid render(id, ...) creates temporary body-level nodes with ids:
      // - id
      // - d{id}  (enclosing div)
      // - i{id}  (iframe in sandbox mode)
      // We render multiple candidates with ids prefixed by generatedDiagramId, so we clean
      // both exact ids and Mermaid-owned prefixes for this diagram only.
      `[id^="${diagramId}-"]`,
      `#d${escapedId}`,
      `[id="d${diagramId}"]`,
      `[id^="d${diagramId}-"]`,
      `#i${escapedId}`,
      `[id="i${diagramId}"]`,
      `[id^="i${diagramId}-"]`,
    ];

    const candidates = new Set<Element>();
    for (const selector of selectors) {
      document.querySelectorAll(selector).forEach((el) => candidates.add(el));
    }

    candidates.forEach((el) => {
      if (!el || el === document.body || el === document.documentElement) return;
      const id = el.id || "";
      // Never remove this component's own React container when matching id prefixes.
      if (id === `${diagramId}-box-container`) return;
      el.remove();
    });
  } catch (e) {
    console.warn("[Mermaid] cleanup artifacts failed", e);
  }
};

const Mermaid: React.FC<MermaidProps> = ({ code }) => {
  // Unique ID for rendering the diagram
  const diagramIdRef = useRef<string>(`mermaid-${Math.random().toString(36).slice(2)}`);
  const generatedDiagramId = diagramIdRef.current;
  const activeSvgUrlRef = useRef<string | null>(null);
  const theme = useTheme();
  const baseCode = applyLangGraphContrastOverrides(
    code.replace(/^mermaid\s*\n/i, "").trim(),
    theme.palette.mode === "dark" ? "dark" : "light"
  );

  // Store the SVG data URI in state (via Blob URL, not innerHTML)
  const [svgSrc, setSvgSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let createdObjectUrl: string | null = null;
    // Candidate 1: raw code (least destructive)
    const rawCandidate = baseCode;
    // Candidate 2: normalize line break markers commonly produced by LLMs
    const htmlBreakCandidate = baseCode
      .replace(/<br\s*\/?>/gi, "<br/>")
      .replace(/\\n/g, "<br/>");
    // Candidate 3: legacy transform kept as fallback for backward compatibility
    const normalized = baseCode.replace(/<br\s*\/?>/gi, "\n");
    const canonical = normalized.replace(/\n\(/g, "<br>(");
    const quoted = canonical.replace(/\[([^[\]"]+)]/g, '["$1"]');
    const preferHtmlBreaks = /\\n|<br\s*\/?>/i.test(baseCode);
    const orderedCandidates = preferHtmlBreaks
      ? [
          { name: "htmlBreaks", code: htmlBreakCandidate },
          { name: "raw", code: rawCandidate },
          { name: "legacyQuoted", code: quoted },
        ]
      : [
          { name: "raw", code: rawCandidate },
          { name: "htmlBreaks", code: htmlBreakCandidate },
          { name: "legacyQuoted", code: quoted },
        ];
    const renderCandidates = uniqueCandidates(orderedCandidates);
    const flowEdgeColor =
      theme.palette.mode === "dark"
        ? alpha(theme.palette.common.white, 0.72)
        : alpha(theme.palette.text.primary, 0.5);
    const flowEdgeWidth = theme.palette.mode === "dark" ? 2.1 : 1.8;

    // Initialize Mermaid with theme-aware colors for readability
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: theme.palette.mode === "dark" ? "dark" : "default",
      flowchart: { htmlLabels: true, useMaxWidth: true },
      themeVariables: {
        primaryColor: theme.palette.primary.main,
        primaryTextColor: theme.palette.getContrastText(theme.palette.primary.main),
        textColor: theme.palette.text.primary,
        lineColor: flowEdgeColor,
        background: theme.palette.background.paper,
        mainBkg: theme.palette.background.paper,
        primaryBorderColor: flowEdgeColor,
        edgeLabelBackground: theme.palette.background.paper,
        noteBkgColor: theme.palette.background.paper,
        noteTextColor: theme.palette.text.primary,
      },
      themeCSS: `
        .edgePath .path,
        path.flowchart-link,
        .flowchart-link,
        path.path {
          stroke: ${flowEdgeColor} !important;
          stroke-width: ${flowEdgeWidth}px !important;
        }

        .arrowheadPath,
        .marker path {
          stroke: ${flowEdgeColor} !important;
          fill: ${flowEdgeColor} !important;
        }
      `,
    } as any);

    const tryRender = async () => {
      let lastErr: unknown = null;
      try {
        if (cancelled) return;
        cleanupMermaidArtifacts(generatedDiagramId);
        let result: Awaited<ReturnType<typeof mermaid.render>> | null = null;
        let strategy: string | null = null;
        let attemptIdx = 0;
        for (const candidate of renderCandidates) {
          if (cancelled) return;
          try {
            const attemptId = `${generatedDiagramId}-${candidate.name}-${attemptIdx++}`;
            console.info(`[Mermaid] rendering diagram (${candidate.name}) with attemptId=${attemptId}`);
            result = await mermaid.render(attemptId, candidate.code);
            if (cancelled) return;
            strategy = candidate.name;
            cleanupMermaidArtifacts(generatedDiagramId);
            break;
          } catch (candidateErr) {
            lastErr = candidateErr;
            if (cancelled) return;
            console.warn(`[Mermaid] render failed (${candidate.name})`, candidateErr);
            cleanupMermaidArtifacts(generatedDiagramId);
          }
        }

        if (!result) {
          throw lastErr ?? new Error("No Mermaid render candidate succeeded");
        }
        if (cancelled) return;

        console.info("[Mermaid] render success strategy=", strategy);

        // Make the SVG responsive: strip fixed width/height, keep viewBox if present
        let responsiveSvg = result.svg.replace(/&nbsp;/g, "&#160;");
        try {
          const parser = new DOMParser();
          const doc = parser.parseFromString(responsiveSvg, "image/svg+xml");
          const parserError = doc.querySelector("parsererror");
          if (parserError || doc.documentElement?.nodeName?.toLowerCase() === "parsererror") {
            throw new Error("SVG XML parse error during Mermaid post-processing");
          }
          const svgEl = doc.documentElement;
          const originalWidth = svgEl.getAttribute("width");
          const originalHeight = svgEl.getAttribute("height");
          const hasViewBox = svgEl.hasAttribute("viewBox");
          const originalWidthNum = parseSvgLength(originalWidth);
          const originalHeightNum = parseSvgLength(originalHeight);
          svgEl.removeAttribute("width");
          svgEl.removeAttribute("height");
          if (!hasViewBox && originalWidthNum && originalHeightNum) {
            svgEl.setAttribute("viewBox", `0 0 ${originalWidthNum} ${originalHeightNum}`);
          }
          svgEl.setAttribute("preserveAspectRatio", "xMidYMid meet");
          const serializer = new XMLSerializer();
          responsiveSvg = serializer.serializeToString(svgEl);
        } catch (e) {
          console.warn("[Mermaid] Could not make SVG responsive", e);
        }

        const blob = new Blob([responsiveSvg], { type: "image/svg+xml" });
        const objectUrl = URL.createObjectURL(blob);
        createdObjectUrl = objectUrl;
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setSvgSrc((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          activeSvgUrlRef.current = objectUrl;
          return objectUrl;
        });
        setError(null);
        setErrorDetails(null);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        console.warn("[Mermaid] render failed", err);
        cleanupMermaidArtifacts(generatedDiagramId);
        setError("Mermaid diagram could not be rendered");
        setErrorDetails(toErrorMessage(err));
        setSvgSrc((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          activeSvgUrlRef.current = null;
          return null;
        });
        setLoading(false);
      }
    };

    // Keep existing diagram while re-rendering to avoid flicker
    setLoading(!svgSrc);
    tryRender();
    return () => {
      cancelled = true;
      cleanupMermaidArtifacts(generatedDiagramId);
      if (createdObjectUrl && createdObjectUrl !== activeSvgUrlRef.current) {
        try {
          URL.revokeObjectURL(createdObjectUrl);
        } catch (e) {
          console.warn("[Mermaid] revoke object URL failed", e);
        }
      }
    };
  }, [baseCode, generatedDiagramId, theme.palette]);

  useEffect(() => {
    return () => {
      const activeUrl = activeSvgUrlRef.current;
      if (!activeUrl) return;
      try {
        URL.revokeObjectURL(activeUrl);
      } catch (e) {
        console.warn("[Mermaid] revoke active object URL on unmount failed", e);
      } finally {
        activeSvgUrlRef.current = null;
      }
    };
  }, []);

  const handleOpenModal = () => setIsModalOpen(true);
  const handleCloseModal = () => setIsModalOpen(false);
  const previewMaxHeight = "60vh";
  const previewSurfaceBg =
    theme.palette.mode === "dark"
      ? theme.palette.background.paper
      : theme.palette.background.paper;
  const previewSurfaceBorder =
    theme.palette.mode === "dark"
      ? `1px solid ${alpha(theme.palette.common.white, 0.14)}`
      : `1px solid ${alpha(theme.palette.common.black, 0.12)}`;
  const toolbarBg =
    theme.palette.mode === "dark"
      ? alpha(theme.palette.common.black, 0.38)
      : alpha(theme.palette.background.paper, 0.9);

  // Save the SVG by creating an <a> link and triggering a download
  const handleSaveSvg = () => {
    if (svgSrc) {
      const link = document.createElement("a");
      link.href = svgSrc;
      link.download = "diagram.svg";
      link.click();
    }
  };

  return (
    <>
      <Box
        id={`${generatedDiagramId}-box-container`}
        style={{
          width: "100%",
          maxWidth: "100%",
          maxHeight: previewMaxHeight,
          overflow: "hidden",
          position: "relative",
          background: previewSurfaceBg,
          border: previewSurfaceBorder,
          borderRadius: 8,
          padding: 10,
          boxSizing: "border-box",
          margin: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {svgSrc && (
          <Box
            sx={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 0.5,
              mb: 1,
            }}
          >
            <Box
              sx={{
                display: "inline-flex",
                alignItems: "center",
                gap: 0.25,
                p: 0.25,
                borderRadius: 999,
                bgcolor: toolbarBg,
                border: (theme) =>
                  `1px solid ${
                    theme.palette.mode === "dark"
                      ? alpha(theme.palette.common.white, 0.06)
                      : theme.palette.divider
                  }`,
                backdropFilter: "blur(6px)",
              }}
            >
              <IconButton onClick={handleOpenModal} size="small">
                <ZoomInIcon fontSize="small" />
              </IconButton>
              <IconButton onClick={handleSaveSvg} size="small">
                <SaveIcon fontSize="small" />
              </IconButton>
            </Box>
          </Box>
        )}

        <Box
          sx={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: 0,
          }}
        >
          {svgSrc ? (
            <img
              src={svgSrc}
              alt="Mermaid Diagram"
              style={{
                display: "block",
                width: "100%",
                maxWidth: "100%",
                maxHeight: "calc(60vh - 48px)",
                height: "auto",
                objectFit: "contain",
                margin: 0,
              }}
            />
          ) : error ? (
            <Box style={{ width: "100%" }}>
              <p style={{ color: "#d32f2f", fontStyle: "italic", marginTop: 0 }}>{error}</p>
              {errorDetails && (
                <p style={{ color: "#b71c1c", opacity: 0.9, marginTop: 4, marginBottom: 8 }}>
                  {errorDetails}
                </p>
              )}
              <p style={{ opacity: 0.8, marginTop: 0, marginBottom: 6 }}>
                Fallback: showing Mermaid source code
              </p>
              <Box
                component="pre"
                sx={{
                  m: 0,
                  p: 1.5,
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "divider",
                  bgcolor: "background.default",
                  color: "text.primary",
                  overflowX: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontFamily: "monospace",
                  fontSize: "0.85rem",
                }}
              >
                {baseCode}
              </Box>
            </Box>
          ) : (
            <p style={{ opacity: 0.7 }}>{loading ? "Loading diagram..." : "Diagram unavailable"}</p>
          )}
        </Box>
      </Box>

      <Modal open={isModalOpen} onClose={handleCloseModal}>
        <Box
          sx={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            width: "80vw",
            height: "80vh",
            bgcolor: "background.paper",
            border: "1px solid #000",
            borderRadius: 3,
            p: 4,
            overflow: "auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {svgSrc && (
            <img
              src={svgSrc}
              alt="Enlarged Diagram"
              style={{
                maxWidth: "100%",
                maxHeight: "100%",
                objectFit: "contain",
              }}
            />
          )}
        </Box>
      </Modal>
    </>
  );
};

export { Mermaid };
export default Mermaid;
