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

import { Box, Dialog, DialogContent, DialogTitle, Divider, IconButton, Tab, Tabs, Typography } from "@mui/material";
import { alpha } from "@mui/material/styles";
import { useEffect, useState } from "react";
import { AnyAgent } from "../../common/agent";
import { useLazyGetAgentGraphTextQuery } from "../../slices/agentic/agenticGraphApi";
import { LoadingSpinner } from "../../utils/loadingSpinner";
import Mermaid from "../markdown/Mermaid";
import CloseIcon from "@mui/icons-material/Close";

interface AgentGraphModalProps {
  agent: AnyAgent | null;
  open: boolean;
  onClose: () => void;
}

export const AgentGraphModal = ({ agent, open, onClose }: AgentGraphModalProps) => {
  const [triggerGetGraph, { data: graph, isLoading, error }] = useLazyGetAgentGraphTextQuery();
  const [tab, setTab] = useState<"rendered" | "mermaid">("rendered");
  const tabPanelHeight = "68vh";

  useEffect(() => {
    if (open && agent) {
      setTab("rendered");
      triggerGetGraph({ agentId: agent.id });
    }
  }, [open, agent, triggerGetGraph]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: {
          backgroundImage: "none",
          bgcolor: (theme) =>
            theme.palette.mode === "dark"
              ? alpha(theme.palette.common.black, 0.72)
              : theme.palette.background.paper,
          border: (theme) =>
            theme.palette.mode === "dark"
              ? `1px solid ${alpha(theme.palette.common.white, 0.16)}`
              : `1px solid ${theme.palette.divider}`,
          backdropFilter: "blur(10px)",
        },
      }}
    >
      <DialogTitle>
        <Typography variant="h6">Agent Graph: {agent?.name}</Typography>
        <IconButton
          aria-label="close"
          onClick={onClose}
          sx={{
            position: "absolute",
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[500],
          }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent
        sx={{
          bgcolor: "transparent",
        }}
      >
        {isLoading && (
          <Box display="flex" justifyContent="center" alignItems="center" minHeight="300px">
            <LoadingSpinner />
          </Box>
        )}
        {error && (
          <Box color="error.main">
            <Typography>Error fetching agent graph.</Typography>
            <pre>{JSON.stringify(error, null, 2)}</pre>
          </Box>
        )}
        {graph && (
          <Box>
            <Tabs
              value={tab}
              onChange={(_, next) => setTab(next)}
              sx={{ mb: 1, "& .MuiTab-root": { textTransform: "none" } }}
            >
              <Tab value="rendered" label="Rendered" />
              <Tab value="mermaid" label="Mermaid" />
            </Tabs>
            <Divider sx={{ mb: 2 }} />
            <Box
              sx={{
                height: tabPanelHeight,
                minHeight: tabPanelHeight,
                maxHeight: tabPanelHeight,
                overflow: "auto",
                p: 0,
                bgcolor: "transparent",
              }}
            >
              {tab === "rendered" ? (
                <Mermaid code={graph} />
              ) : (
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    p: 2,
                    borderRadius: 1,
                    bgcolor: (theme) =>
                      theme.palette.mode === "dark"
                        ? alpha(theme.palette.common.black, 0.38)
                        : theme.palette.background.paper,
                    border: (theme) => `1px solid ${theme.palette.divider}`,
                    overflow: "auto",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    fontSize: 13,
                    fontFamily:
                      "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                    minHeight: `calc(${tabPanelHeight} - 2px)`,
                    boxSizing: "border-box",
                  }}
                >
                  {graph}
                </Box>
              )}
            </Box>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
};
