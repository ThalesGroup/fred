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

import React, { useEffect, useState } from 'react';
import mermaid from 'mermaid';
import { v4 as uuidv4 } from 'uuid';
import { Box, IconButton, Modal } from '@mui/material';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import SaveIcon from '@mui/icons-material/Save';

interface MermaidProps {
  code: string;
}

const Mermaid: React.FC<MermaidProps> = ({ code }) => {
  // Unique ID for rendering the diagram
  const generatedDiagramId = `mermaid-${uuidv4()}`;

  // Store the SVG data URI in state
  const [svgSrc, setSvgSrc] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    // Initialize Mermaid
    mermaid.initialize({ startOnLoad: false });

    // Render diagram
    mermaid
      .render(generatedDiagramId, code)
      .then((result) => {
        // If we successfully render, build a data URI for the SVG
        const newSvgSrc = `data:image/svg+xml;utf8,${encodeURIComponent(result.svg)}`;
        setSvgSrc(newSvgSrc);
      })
      .catch((error) => {
        console.error(error);
        // If there's an error, optionally show a fallback message or keep svgSrc as null
        setSvgSrc(null);
      });
  }, [code, generatedDiagramId]);

  const handleOpenModal = () => setIsModalOpen(true);
  const handleCloseModal = () => setIsModalOpen(false);

  // Save the SVG by creating an <a> link and triggering a download
  const handleSaveSvg = () => {
    if (svgSrc) {
      const link = document.createElement('a');
      link.href = svgSrc;
      link.download = 'diagram.svg';
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
        style={{ maxWidth: '100%', maxHeight: '800px', overflow: 'auto', position: 'relative' }}
      >
        {svgSrc ? <img src={svgSrc} alt="Mermaid Diagram" /> : <p>Loading diagram...</p>}
      </Box>

      <Modal open={isModalOpen} onClose={handleCloseModal}>
        <Box
          sx={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '80vw',
            height: '80vh',
            bgcolor: 'background.paper',
            border: '1px solid #000',
            borderRadius: 3,
            p: 4,
            overflow: 'auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {svgSrc && (
            <img
              src={svgSrc}
              alt="Enlarged Diagram"
              style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
            />
          )}
        </Box>
      </Modal>
    </>
  );
};

export default Mermaid;
