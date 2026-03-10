import CloseIcon from "@mui/icons-material/Close";
import InsightsIcon from "@mui/icons-material/Insights";
import PrecisionManufacturingIcon from "@mui/icons-material/PrecisionManufacturing";
import SettingsSuggestIcon from "@mui/icons-material/SettingsSuggest";
import {
  Alert,
  Box,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Grid,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import { useEffect } from "react";

import { AnyAgent } from "../../common/agent";
import { useLazyGetAgentInspectionQuery } from "../../slices/agentic/agenticInspectionApi";
import { LoadingSpinner } from "../../utils/loadingSpinner";

interface AgentInspectionModalProps {
  agent: AnyAgent | null;
  open: boolean;
  onClose: () => void;
}

const EXECUTION_LABEL: Record<string, string> = {
  react: "ReAct runtime",
  graph: "Graph runtime",
  proxy: "Proxy runtime",
};

const Section = ({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) => (
  <Stack
    spacing={1.25}
    sx={{
      p: 2,
      borderRadius: 2,
      border: (theme) => `1px solid ${theme.palette.divider}`,
      bgcolor: (theme) =>
        theme.palette.mode === "dark"
          ? alpha(theme.palette.common.black, 0.18)
          : alpha(theme.palette.common.white, 0.68),
      minHeight: "100%",
    }}
  >
    <Stack direction="row" spacing={1} alignItems="center">
      {icon}
      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
        {title}
      </Typography>
    </Stack>
    {children}
  </Stack>
);

const EmptyState = ({ text }: { text: string }) => (
  <Typography variant="body2" color="text.secondary">
    {text}
  </Typography>
);

export const AgentInspectionModal = ({ agent, open, onClose }: AgentInspectionModalProps) => {
  const [triggerGetInspection, { data: inspection, isLoading, error }] = useLazyGetAgentInspectionQuery();

  useEffect(() => {
    if (open && agent) {
      triggerGetInspection({ agentId: agent.id });
    }
  }, [open, agent, triggerGetInspection]);

  const tags = inspection?.tags ?? [];
  const fields = inspection?.fields ?? [];
  const tools = inspection?.tool_requirements ?? [];
  const defaultMcpServers = inspection?.default_mcp_servers ?? [];

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
      <DialogTitle sx={{ pr: 6 }}>
        <Stack spacing={1}>
          <Typography variant="h6">Agent inspection: {agent?.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            Safe definition summary only. No runtime activation, no graph rendering.
          </Typography>
        </Stack>
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
      <DialogContent sx={{ bgcolor: "transparent" }}>
        {isLoading && (
          <Box display="flex" justifyContent="center" alignItems="center" minHeight="300px">
            <LoadingSpinner />
          </Box>
        )}

        {!isLoading && error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to inspect this agent. This view is only available for v2 agent definitions.
          </Alert>
        )}

        {!isLoading && inspection && (
          <Stack spacing={2}>
            <Section icon={<InsightsIcon fontSize="small" color="primary" />} title="Identity">
              <Stack spacing={1}>
                <Typography variant="body1" sx={{ fontWeight: 700 }}>
                  {inspection.role}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {inspection.description}
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip size="small" label={EXECUTION_LABEL[inspection.execution_category] ?? inspection.execution_category} />
                  {tags.map((tag) => (
                    <Chip key={tag} size="small" variant="outlined" label={tag} />
                  ))}
                </Stack>
              </Stack>
            </Section>

            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <Section icon={<SettingsSuggestIcon fontSize="small" color="primary" />} title="Tuning surface">
                  {fields.length === 0 ? (
                    <EmptyState text="No exposed tuning fields." />
                  ) : (
                    <Stack spacing={1}>
                      {fields.map((field) => (
                        <Box key={field.key} sx={{ pb: 1, borderBottom: (theme) => `1px dashed ${theme.palette.divider}` }}>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>
                            {field.title || field.key}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {field.description || field.type || "Exposed tuning field"}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  )}
                </Section>
              </Grid>

              <Grid item xs={12} md={6}>
                <Section icon={<PrecisionManufacturingIcon fontSize="small" color="primary" />} title="Declared capabilities">
                  {tools.length === 0 && defaultMcpServers.length === 0 ? (
                    <EmptyState text="No declared tools or default MCP servers." />
                  ) : (
                    <Stack spacing={1.5}>
                      {tools.length > 0 && (
                        <Stack spacing={1}>
                          <Typography variant="caption" color="text.secondary">
                            Tool requirements
                          </Typography>
                          {tools.map((tool, index) => (
                            <Box key={`${tool.kind}-${index}`}>
                              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                {tool.kind === "tool_ref" ? tool.tool_ref : tool.capability}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {tool.kind === "tool_ref" ? "Declared tool" : "Required capability"}
                                {tool.required === false ? " · optional" : " · required"}
                                {tool.description ? ` · ${tool.description}` : ""}
                              </Typography>
                            </Box>
                          ))}
                        </Stack>
                      )}

                      {defaultMcpServers.length > 0 && (
                        <>
                          {tools.length > 0 && <Box sx={{ borderTop: (theme) => `1px solid ${theme.palette.divider}` }} />}
                          <Stack spacing={1}>
                            <Typography variant="caption" color="text.secondary">
                              Default MCP servers
                            </Typography>
                            {defaultMcpServers.map((server) => (
                              <Box key={server.id}>
                                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                  {server.id}
                                </Typography>
                                {server.require_tools && server.require_tools.length > 0 && (
                                  <Typography variant="caption" color="text.secondary">
                                    Requires tools: {server.require_tools.join(", ")}
                                  </Typography>
                                )}
                              </Box>
                            ))}
                          </Stack>
                        </>
                      )}
                    </Stack>
                  )}
                </Section>
              </Grid>

            </Grid>
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  );
};
