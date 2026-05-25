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

import { Dialog, DialogTitle, DialogContent, DialogActions, Button, Box, Stack, Typography } from "@mui/material";
import * as React from "react";
import type { Resource } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

function splitFrontMatter(text: string) {
  const norm = (text || "").replace(/\r\n/g, "\n");
  const idx = norm.indexOf("\n---\n");
  if (idx === -1) return { headerText: "", body: norm };
  return { headerText: norm.slice(0, idx).trim(), body: norm.slice(idx + 5) };
}

type Props = { open: boolean; resource: Resource | null; onClose: () => void };

export const ResourcePreviewModal: React.FC<Props> = ({ open, resource, onClose }) => {
  if (!resource) return null;
  const { body } = splitFrontMatter(resource.content || "");
  const updated = resource.updated_at ? new Date(resource.updated_at).toLocaleString() : "-";

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{resource.name || "(untitled)"} — preview</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Kind: {resource.kind} • Updated: {updated}
          </Typography>
          <Box component="pre" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace", m: 0 }}>
            {body}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};
