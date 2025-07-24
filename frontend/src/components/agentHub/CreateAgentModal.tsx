import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  MenuItem,
  IconButton,
  Grid2,
  Box,
} from "@mui/material";
import RobotIcon from "@mui/icons-material/SmartToy";
import ChipIcon from "@mui/icons-material/Memory";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import EmojiObjectsIcon from "@mui/icons-material/EmojiObjects";

import DeleteIcon from "@mui/icons-material/Delete";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCreateAgentMutation } from "../../slices/chatApi";
import {
  AgentType,
  CreateAgentRequest,
  McpServer,
  McpTransport,
} from "../../slices/chatApiStructures";
import { useToast } from "../ToastProvider";

interface CreateAgentModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

const agentTypes: AgentType[] = ["mcp", "langgraph", "planning"];
const transportOptions: McpTransport[] = ["sse", "http"];
const iconOptions = [
  { label: "Robot", icon: <RobotIcon fontSize="small" /> },
  { label: "Chip", icon: <ChipIcon fontSize="small" /> },
  { label: "AutoAwesome", icon: <AutoAwesomeIcon fontSize="small" /> },
  { label: "EmojiObjects", icon: <EmojiObjectsIcon fontSize="small" /> },
];
const initialForm: Omit<CreateAgentRequest, "mcp_servers"> = {
  name: "",
  nickname: "",
  description: "",
  role: "",
  base_prompt: "",
  tag: "",
  icon: "Robot",
  agent_type: "mcp",
  categories: [],
};

export const CreateAgentModal = ({
  open,
  onClose,
  onCreated,
}: CreateAgentModalProps) => {
    const { showError } = useToast();

  const { t } = useTranslation();
  const [form, setForm] = useState<Omit<CreateAgentRequest, "mcp_servers">>(
    initialForm
  );
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createAgent] = useCreateAgentMutation();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await createAgent({
        ...form,
        mcp_servers: mcpServers,
      }).unwrap();

      onCreated();
      setForm(initialForm);
      setMcpServers([]);
    } catch (error) {
      console.error("Error creating agent:", error);
      showError({
    summary: "Agent creation failed",
    detail: error?.data?.detail || error.message || "An unexpected error occurred.",
  });
    } finally {
      setIsSubmitting(false);
    }
  };

  const updateMcpServer = (index: number, updated: McpServer) => {
    setMcpServers((prev) => {
      const copy = [...prev];
      copy[index] = updated;
      return copy;
    });
  };

  const removeMcpServer = (index: number) => {
    setMcpServers((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{t("agentHub.create")}</DialogTitle>
      <DialogContent dividers sx={{ px: 4 }}>
        <Grid2 container spacing={2}>
          {["name", "nickname", "description", "role", "tag"].map((field) => (
            <Grid2 size={{ xs: 12, sm: 6 }} key={field}>
              <TextField
                fullWidth
                size="small"
                label={t(`agentHub.fields.${field}`, field)}
                name={field}
                value={form[field as keyof typeof form]}
                onChange={handleChange}
              />
            </Grid2>
          ))}

          <Grid2 size={{ xs: 12 }}>
            <TextField
              fullWidth
              multiline
              minRows={5}
              maxRows={20}
              size="small"
              label={t("agentHub.fields.base_prompt", "Base Prompt")}
              name="base_prompt"
              value={form.base_prompt}
              onChange={handleChange}
            />
          </Grid2>

          <Grid2 size={{ xs: 12, sm: 6 }}>
            <TextField
              select
              fullWidth
              size="small"
              label={t("agentHub.fields.agent_type", "Agent Type")}
              name="agent_type"
              value={form.agent_type}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  agent_type: e.target.value as AgentType,
                }))
              }
            >
              {agentTypes.map((type) => (
                <MenuItem key={type} value={type}>
                  {type}
                </MenuItem>
              ))}
            </TextField>
          </Grid2>

          <Grid2 size={{ xs: 12, sm: 6 }}>
            <TextField
  select
  fullWidth
  size="small"
  label={t("agentHub.fields.icon", "Icon")}
  name="icon"
  value={form.icon}
  onChange={handleChange}
>
  {iconOptions.map((option) => (
    <MenuItem key={option.label} value={option.label}>
      <Box display="flex" alignItems="center" gap={1}>
        {option.icon}
        {option.label}
      </Box>
    </MenuItem>
  ))}
</TextField>

          </Grid2>

          {form.agent_type === "mcp" && (
            <>
              <Grid2 size={{ xs: 12 }}>
                <strong>MCP Servers</strong>
              </Grid2>

              {mcpServers.map((server, index) => (
                <Grid2
                  container
                  spacing={1}
                  key={index}
                  wrap="nowrap"
                  alignItems="center"
                >
                  <Grid2 sx={{ width: 150 }}>
                    <TextField
                      label="Name"
                      fullWidth
                      size="small"
                      value={server.name}
                      onChange={(e) =>
                        updateMcpServer(index, {
                          ...server,
                          name: e.target.value,
                        })
                      }
                    />
                  </Grid2>
                  <Grid2 sx={{ flexGrow: 1 }}>
                    <TextField
                      label="URL"
                      fullWidth
                      size="small"
                      value={server.url}
                      onChange={(e) =>
                        updateMcpServer(index, {
                          ...server,
                          url: e.target.value,
                        })
                      }
                    />
                  </Grid2>
                  <Grid2 sx={{ width: 140 }}>
                    <TextField
                      select
                      fullWidth
                      size="small"
                      label="Transport"
                      value={server.transport ?? "sse"}
                      onChange={(e) =>
                        updateMcpServer(index, {
                          ...server,
                          transport: e.target.value as McpTransport,
                        })
                      }
                    >
                      {transportOptions.map((value) => (
                        <MenuItem key={value} value={value}>
                          {value}
                        </MenuItem>
                      ))}
                    </TextField>
                  </Grid2>
                  <Grid2 sx={{ width: 100 }}>
                    <TextField
                      label="Timeout"
                      type="number"
                      size="small"
                      fullWidth
                      value={server.sse_read_timeout ?? ""}
                      onChange={(e) =>
                        updateMcpServer(index, {
                          ...server,
                          sse_read_timeout: Number(e.target.value),
                        })
                      }
                    />
                  </Grid2>
                  <Grid2>
                    <IconButton
                      onClick={() => removeMcpServer(index)}
                      size="small"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Grid2>
                </Grid2>
              ))}

              <Grid2 size={{ xs: 12 }}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() =>
                    setMcpServers((prev) => [
                      ...prev,
                      {
                        name: "",
                        url: "",
                        transport: "sse",
                        sse_read_timeout: 600,
                      },
                    ])
                  }
                >
                  + Add MCP Server
                </Button>
              </Grid2>
            </>
          )}
        </Grid2>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose}>
          {t("common.cancel", "Cancel")}
        </Button>
        <Button
          size="small"
          onClick={handleSubmit}
          disabled={isSubmitting}
          variant="contained"
        >
          {t("common.create", "Create")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
