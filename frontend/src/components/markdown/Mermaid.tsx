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
import { useTheme } from "@mui/material/styles";

interface MermaidProps {
  code: string;
}

interface MermaidRenderCandidate {
  name: string;
  code: string;
}

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
  const baseCode = code.replace(/^mermaid\s*\n/i, "").trim();

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

    // Initialize Mermaid with theme-aware colors for readability
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: theme.palette.mode === "dark" ? "dark" : "default",
      flowchart: { htmlLabels: true, useMaxWidth: true },
      themeVariables: {
        primaryColor: theme.palette.primary.main,
        primaryTextColor: theme.palette.getContrastText(theme.palette.primary.main),
        lineColor: theme.palette.divider,
        background: theme.palette.background.paper,
        noteBkgColor: theme.palette.background.paper,
        noteTextColor: theme.palette.text.primary,
      },
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
        let responsiveSvg = result.svg;
        try {
          const parser = new DOMParser();
          const doc = parser.parseFromString(result.svg, "image/svg+xml");
          const svgEl = doc.documentElement;
          svgEl.removeAttribute("width");
          svgEl.removeAttribute("height");
          if (!svgEl.getAttribute("viewBox") && svgEl.hasAttribute("width") && svgEl.hasAttribute("height")) {
            const w = svgEl.getAttribute("width");
            const h = svgEl.getAttribute("height");
            if (w && h) {
              svgEl.setAttribute("viewBox", `0 0 ${w} ${h}`);
            }
          }
          svgEl.setAttribute("width", "100%");
          svgEl.setAttribute("height", "auto");
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
      {/* Only show buttons if we have a valid SVG to display */}
      {svgSrc && (
        <>
          <IconButton onClick={handleOpenModal}>
            <ZoomInIcon />
          </IconButton>
          <IconButton onClick={handleSaveSvg}>
            <SaveIcon />
          </IconButton>
        </>
      )}

      <Box
        id={`${generatedDiagramId}-box-container`}
        style={{
          width: "100%",
          maxWidth: "100%",
          overflow: "hidden",
          position: "relative",
          border: "1px solid rgba(0,0,0,0.08)",
          borderRadius: 8,
          padding: 8,
          boxSizing: "border-box",
          margin: "8px 0",
          display: "flex",
          justifyContent: "center",
        }}
      >
        {svgSrc ? (
          <img
            src={svgSrc}
            alt="Mermaid Diagram"
            style={{ display: "block", maxWidth: "100%", height: "auto", margin: 0 }}
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

export default Mermaid;
