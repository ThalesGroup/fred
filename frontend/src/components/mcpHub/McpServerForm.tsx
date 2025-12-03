// Copyright Thales 2025

import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ClientAuthMode, McpServerConfiguration } from "../../slices/agentic/agenticOpenApi";

export interface McpServerFormProps {
  open: boolean;
  initial?: McpServerConfiguration | null;
  onCancel: () => void;
  onSubmit: (server: McpServerConfiguration) => void;
}

type Draft = McpServerConfiguration;

const DEFAULT_SERVER: Draft = {
  id: "",
  name: "",
  transport: "streamable_http",
  enabled: true,
  auth_mode: "user_token",
  sse_read_timeout: 300,
};

const transportOptions = ["streamable_http", "sse", "websocket", "stdio"];
const authOptions: ClientAuthMode[] = ["user_token", "no_token"];

function argsToText(args?: string[] | null): string {
  return (args || []).join(" ");
}

function envToText(env?: Record<string, string> | null): string {
  if (!env) return "";
  return Object.entries(env)
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
}

function parseArgs(raw: string): string[] | undefined {
  const tokens = raw
    .split(/[\s,]+/)
    .map((t) => t.trim())
    .filter(Boolean);
  return tokens.length ? tokens : undefined;
}

function parseEnv(raw: string): Record<string, string> | undefined {
  const lines = raw
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return undefined;

  const env: Record<string, string> = {};
  for (const line of lines) {
    const idx = line.indexOf("=");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    if (key) env[key] = value;
  }
  return Object.keys(env).length ? env : undefined;
}

export function McpServerForm({ open, initial, onCancel, onSubmit }: McpServerFormProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<Draft>(DEFAULT_SERVER);
  const [argsText, setArgsText] = useState("");
  const [envText, setEnvText] = useState("");

  useEffect(() => {
    const base = initial ?? DEFAULT_SERVER;
    setDraft({
      ...DEFAULT_SERVER,
      ...base,
    });
    setArgsText(argsToText(base.args));
    setEnvText(envToText(base.env));
  }, [initial, open]);

  const isStdio = useMemo(() => (draft.transport || "").toLowerCase() === "stdio", [draft.transport]);

  const handleSubmit = () => {
    const cleaned: Draft = {
      ...draft,
      id: draft.id.trim(),
      name: draft.name.trim(),
      description: draft.description?.trim() || undefined,
      url: draft.url?.trim() || undefined,
      command: draft.command?.trim() || undefined,
      args: parseArgs(argsText),
      env: parseEnv(envText),
      sse_read_timeout: draft.sse_read_timeout || undefined,
    };
    if (!cleaned.id || !cleaned.name) {
      return;
    }
    onSubmit(cleaned);
  };

  return (
    <Dialog open={open} onClose={onCancel} maxWidth="md" fullWidth>
      <DialogTitle>{initial ? t("mcpHub.editTitle") : t("mcpHub.addTitle")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label={t("mcpHub.fields.id")}
              fullWidth
              required
              value={draft.id}
              onChange={(e) => setDraft({ ...draft, id: e.target.value })}
            />
            <TextField
              label={t("mcpHub.fields.name")}
              fullWidth
              required
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </Stack>

          <TextField
            label={t("mcpHub.fields.description")}
            fullWidth
            multiline
            minRows={2}
            value={draft.description || ""}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          />

          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <FormControl fullWidth>
              <InputLabel id="transport-label">{t("mcpHub.fields.transport")}</InputLabel>
              <Select
                labelId="transport-label"
                label={t("mcpHub.fields.transport")}
                value={draft.transport || "streamable_http"}
                onChange={(e) => setDraft({ ...draft, transport: e.target.value })}
              >
                {transportOptions.map((opt) => (
                  <MenuItem key={opt} value={opt}>
                    {t(`mcpHub.transport.${opt}`, opt)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="auth-mode-label">{t("mcpHub.fields.auth_mode")}</InputLabel>
              <Select
                labelId="auth-mode-label"
                label={t("mcpHub.fields.auth_mode")}
                value={draft.auth_mode || "user_token"}
                onChange={(e) => setDraft({ ...draft, auth_mode: e.target.value as ClientAuthMode })}
              >
                {authOptions.map((opt) => (
                  <MenuItem key={opt} value={opt}>
                    {t(`mcpHub.auth.${opt}`, opt)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label={t("mcpHub.fields.timeout")}
              type="number"
              fullWidth
              value={draft.sse_read_timeout ?? ""}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  sse_read_timeout: e.target.value === "" ? undefined : Number(e.target.value),
                })
              }
            />
          </Stack>

          {isStdio ? (
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label={t("mcpHub.fields.command")}
                fullWidth
                value={draft.command || ""}
                onChange={(e) => setDraft({ ...draft, command: e.target.value })}
              />
              <TextField
                label={t("mcpHub.fields.args")}
                fullWidth
                value={argsText}
                onChange={(e) => setArgsText(e.target.value)}
                helperText={t("mcpHub.helpers.args")}
              />
            </Stack>
          ) : (
            <TextField
              label={t("mcpHub.fields.url")}
              fullWidth
              value={draft.url || ""}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
            />
          )}

          <TextField
            label={t("mcpHub.fields.env")}
            fullWidth
            multiline
            minRows={3}
            value={envText}
            onChange={(e) => setEnvText(e.target.value)}
            helperText={t("mcpHub.helpers.env")}
          />

          <Box>
            <FormControlLabel
              control={
                <Switch
                  checked={draft.enabled !== false}
                  onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
                />
              }
              label={t("mcpHub.fields.enabled")}
            />
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onCancel}>{t("common.cancel")}</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={!draft.id.trim() || !draft.name.trim()}>
          {t("common.save")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
