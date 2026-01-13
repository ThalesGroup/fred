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

const Mermaid: React.FC<MermaidProps> = ({ code }) => {
  // Unique ID for rendering the diagram
  const diagramIdRef = useRef<string>(`mermaid-${Math.random().toString(36).slice(2)}`);
  const generatedDiagramId = diagramIdRef.current;
  const theme = useTheme();

  // Store the SVG data URI in state (via Blob URL, not innerHTML)
  const [svgSrc, setSvgSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Normalize common wrappers (e.g., leading "mermaid\n" from some generators)
    const base = code.replace(/^mermaid\s*\n/i, "").trim();
    // Convert <br> or <br/> tags to newline for Mermaid compatibility
    const normalized = base.replace(/<br\s*\/?>/gi, "\n");
    // Mermaid flowchart labels cannot contain raw newlines inside brackets; convert to <br>
    const canonical = normalized.replace(/\n\(/g, "<br>(");
    // Wrap bare labels in quotes to allow HTML/parentheses safely
    const quoted = canonical.replace(/\[([^[\]"]+)]/g, '["$1"]');
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
      try {
        console.info("[Mermaid] rendering diagram:\n", quoted);
        const result = await mermaid.render(generatedDiagramId, quoted);

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
        setSvgSrc((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return objectUrl;
        });
        setError(null);
        setLoading(false);
      } catch (err) {
        console.warn("[Mermaid] render failed", err);
        setError("Mermaid diagram could not be rendered (syntax error)");
        setSvgSrc((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return null;
        });
        setLoading(false);
      }
    };

    // Keep existing diagram while re-rendering to avoid flicker
    setLoading(!svgSrc);
    tryRender();
    return () => {
      setSvgSrc((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [code, generatedDiagramId, theme.palette]);

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
          <p style={{ color: "#d32f2f", fontStyle: "italic" }}>{error}</p>
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
