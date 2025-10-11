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

import { zodResolver } from "@hookform/resolvers/zod";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  TextField,
  Typography,
} from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import React, { useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

// OpenAPI-generated types & hook (regenerated)
import {
  CreateMcpAgentRequest,
  McpServerConfiguration,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
} from "../../slices/agentic/agenticOpenApi";

import { useToast } from "../ToastProvider";
import { createMcpAgentSchema, MCP_TRANSPORTS } from "./agentSchema";

type FormData = z.infer<ReturnType<typeof createMcpAgentSchema>>;

interface CreateAgentModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export const CreateAgentModal: React.FC<CreateAgentModalProps> = ({ open, onClose, onCreated }) => {
  const { t } = useTranslation();
  const schema = createMcpAgentSchema(t);
  const { showError, showSuccess } = useToast();
  const [createAgent, { isLoading }] = useCreateAgentAgenticV1AgentsCreatePostMutation();

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
    setValue,
    watch,
    reset,
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      role: "",
      description: "",
      tags: [],
      mcp_servers: [{ name: "", transport: "streamable_http", url: "", sse_read_timeout: 600 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "mcp_servers" });
  const tags = watch("tags") || [];

  // Small controlled “chips” UX for tags
  const [customTag, setCustomTag] = useState("");

  const addTag = () => {
    const v = customTag.trim();
    if (!v) return;
    if (!tags.includes(v)) setValue("tags", [...tags, v]);
    setCustomTag("");
  };

  // For each server, allow showing/hiding advanced fields
  const [openAdvanced, setOpenAdvanced] = useState<Record<string, boolean>>({});

  const submit = async (data: FormData) => {
    // Map to CreateMcpAgentRequest, removing empty strings (→ null)
    const clean = (s?: string | null) => (s && s.trim().length ? s.trim() : null);

    const req: CreateMcpAgentRequest = {
      name: data.name.trim(),
      role: data.role.trim(),
      description: data.description.trim(),
      tags: data.tags && data.tags.length ? data.tags : null,
      mcp_servers: data.mcp_servers.map<McpServerConfiguration>((s) => ({
        name: s.name.trim(),
        transport: s.transport ?? null,
        url: clean(s.url ?? null),
        sse_read_timeout: s.sse_read_timeout ?? null,
      })),
    };

    try {
      // NOTE: After regeneration, most generators accept the request object directly.
      // If your generated endpoint expects `{ body: req }`, adjust accordingly.
      await createAgent({ createMcpAgentRequest: req }).unwrap();
      onCreated();
      reset();
      onClose();
      showSuccess({
        summary: t("agentHub.messages.creationSuccess", "Agent created"),
        detail: t("agentHub.messages.creationSuccessDetail", "The MCP agent was created successfully."),
      });
    } catch (e: any) {
      showError({
        title: t("agentHub.errors.creationFailed", "MCP Agent Creation failed"),
        summary: t("agentHub.errors.creationFailedDetail", "Failed to create MCP Agent. See console."),
        // For devs: show raw error in detail (hover tooltip)
        detail: "MCP agent creation error: " + (e?.data?.detail || e.message || e.toString()),
      });
      console.error("Create MCP agent failed:", e);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{t("agentHub.createMcpAgent", "Create MCP agent")}</DialogTitle>
      <DialogContent dividers>
        <form onSubmit={handleSubmit(submit)}>
          <Grid2 container spacing={2}>
            {(["name", "role"] as const).map((field) => (
              <Grid2 key={field} size={{ xs: 12, sm: 6 }}>
                <Controller
                  name={field}
                  control={control}
                  render={({ field: f }) => (
                    <TextField
                      {...f}
                      fullWidth
                      size="small"
                      required
                      label={t(`agentHub.fields.${field}`, field)}
                      error={!!errors[field]}
                      helperText={(errors[field]?.message as string) || ""}
                    />
                  )}
                />
              </Grid2>
            ))}

            <Grid2 size={12}>
              <Controller
                name="description"
                control={control}
                render={({ field }) => (
                  <TextField
                    {...field}
                    fullWidth
                    size="small"
                    multiline
                    minRows={3}
                    label={t("agentHub.fields.description", "Description")}
                    error={!!errors.description}
                    helperText={(errors.description?.message as string) || ""}
                  />
                )}
              />
            </Grid2>

            {/* Tags */}
            <Grid2 size={12}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t("agentHub.fields.tags", "Tags")}
              </Typography>
              <Box display="flex" flexWrap="wrap" gap={1} mb={1}>
                {tags.map((tag) => (
                  <Chip
                    key={tag}
                    label={tag}
                    size="small"
                    onDelete={() =>
                      setValue(
                        "tags",
                        tags.filter((t) => t !== tag),
                      )
                    }
                  />
                ))}
              </Box>
              <Box display="flex" gap={1}>
                <TextField
                  value={customTag}
                  onChange={(e) => setCustomTag(e.target.value)}
                  size="small"
                  label={t("agentHub.fields.custom_tag", "Add custom tag")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addTag();
                    }
                  }}
                />
                <Button variant="outlined" size="small" startIcon={<AddIcon />} onClick={addTag}>
                  {t("agentHub.actions.add_tag", "Add tag")}
                </Button>
              </Box>
            </Grid2>

            {/* MCP Servers */}
            <Grid2 size={12}>
              <Typography fontWeight="bold" sx={{ mb: 1 }}>
                {t("agentHub.fields.mcp_servers", "MCP Servers")}
              </Typography>

              {fields.map((row, index) => {
                const advKey = row.id;
                const showAdv = !!openAdvanced[advKey];

                return (
                  <Box
                    key={row.id}
                    sx={{
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1.5,
                      p: 1,
                      mb: 1,
                    }}
                  >
                    <Grid2 container spacing={1} alignItems="center" wrap="wrap">
                      {/* name */}
                      <Grid2 size={{ xs: 12, md: 2.5 }}>
                        <Controller
                          name={`mcp_servers.${index}.name`}
                          control={control}
                          render={({ field }) => (
                            <TextField
                              {...field}
                              fullWidth
                              size="small"
                              label={t("agentHub.fields.mcp_server.name", "Name")}
                              error={!!errors.mcp_servers?.[index]?.name}
                              helperText={errors.mcp_servers?.[index]?.name?.message as string}
                            />
                          )}
                        />
                      </Grid2>

                      {/* transport */}
                      <Grid2 size={{ xs: 12, md: 2.5 }}>
                        <Controller
                          name={`mcp_servers.${index}.transport`}
                          control={control}
                          render={({ field }) => (
                            <TextField
                              {...field}
                              select
                              fullWidth
                              size="small"
                              label={t("agentHub.fields.mcp_server.transport", "Transport")}
                              error={!!errors.mcp_servers?.[index]?.transport}
                              helperText={errors.mcp_servers?.[index]?.transport?.message as string}
                            >
                              {MCP_TRANSPORTS.map((opt) => (
                                <MenuItem key={opt} value={opt}>
                                  {opt}
                                </MenuItem>
                              ))}
                            </TextField>
                          )}
                        />
                      </Grid2>

                      {/* url */}
                      <Grid2 size={{ xs: 12, md: 4 }}>
                        <Controller
                          name={`mcp_servers.${index}.url`}
                          control={control}
                          render={({ field }) => (
                            <TextField
                              {...field}
                              fullWidth
                              size="small"
                              label={t("agentHub.fields.mcp_server.url", "URL")}
                              error={!!errors.mcp_servers?.[index]?.url}
                              helperText={errors.mcp_servers?.[index]?.url?.message as string}
                              placeholder="http://localhost:8111/mcp"
                            />
                          )}
                        />
                      </Grid2>

                      {/* timeout */}
                      <Grid2 size={{ xs: 7, md: 2 }}>
                        <Controller
                          name={`mcp_servers.${index}.sse_read_timeout`}
                          control={control}
                          render={({ field }) => (
                            <TextField
                              {...field}
                              type="number"
                              fullWidth
                              size="small"
                              label={t("agentHub.fields.mcp_server.timeout", "SSE timeout (s)")}
                              inputProps={{ min: 0, step: 1 }}
                              value={field.value ?? ""}
                              onChange={(e) => {
                                const v = (e.target as HTMLInputElement).value;
                                field.onChange(v === "" ? null : Number(v));
                              }}
                              error={!!errors.mcp_servers?.[index]?.sse_read_timeout}
                              helperText={errors.mcp_servers?.[index]?.sse_read_timeout?.message as string}
                            />
                          )}
                        />
                      </Grid2>

                      {/* actions */}
                      <Grid2 size={{ xs: 5, md: 1 }} display="flex" justifyContent="flex-end" alignItems="center">
                        <IconButton
                          size="small"
                          onClick={() => setOpenAdvanced((s) => ({ ...s, [advKey]: !s[advKey] }))}
                          title={t("agentHub.actions.advanced", "Advanced") as string}
                        >
                          <ExpandMoreIcon
                            sx={{
                              transform: showAdv ? "rotate(180deg)" : "rotate(0deg)",
                              transition: "transform 0.2s",
                            }}
                          />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => remove(index)}
                          title={t("common.delete", "Delete") as string}
                        >
                          <DeleteIcon />
                        </IconButton>
                      </Grid2>
                    </Grid2>
                  </Box>
                );
              })}

              <Button
                variant="outlined"
                size="small"
                startIcon={<AddIcon />}
                onClick={() => append({ name: "", transport: "streamable_http", url: "", sse_read_timeout: 600 })}
              >
                {t("agentHub.actions.add_mcp_server", "+ Add MCP Server")}
              </Button>
            </Grid2>
          </Grid2>

          <DialogActions sx={{ mt: 1 }}>
            <Button size="small" onClick={onClose} disabled={isLoading || isSubmitting}>
              {t("dialogs.cancel", "Cancel")}
            </Button>
            <Button size="small" type="submit" variant="contained" disabled={isLoading || isSubmitting}>
              {t("dialogs.create.confirm", "Create")}
            </Button>
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
};
