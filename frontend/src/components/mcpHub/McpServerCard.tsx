// Copyright Thales 2025

import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import HttpIcon from "@mui/icons-material/Http";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import TerminalRounded from "@mui/icons-material/TerminalRounded";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import {
  Card,
  CardContent,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import { McpServerConfiguration } from "../../slices/agentic/agenticOpenApi";

export interface McpServerCardProps {
  server: McpServerConfiguration;
  onEdit: (server: McpServerConfiguration) => void;
  onDelete: (server: McpServerConfiguration) => void;
  canEdit: boolean;
  canDelete: boolean;
  onToggleEnabled?: (server: McpServerConfiguration) => void;
}

export function McpServerCard({
  server,
  onEdit,
  onDelete,
  canEdit,
  canDelete,
  onToggleEnabled,
}: McpServerCardProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const transport = (server.transport || "streamable_http").toLowerCase();
  const isStdio = transport === "stdio";
  const connectionDetail = isStdio
    ? [server.command, ...(server.args || [])].filter(Boolean).join(" ") || "—"
    : server.url || "—";

  return (
    <Card
      variant="outlined"
      sx={{
        height: "100%",
        borderRadius: 2,
        opacity: server.enabled === false ? 0.4 : 1,
      }}
    >
      <CardContent>
        <Stack spacing={1}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="h6">{t(server.name)}</Typography>
            <Chip
              size="small"
              label={transport}
              icon={isStdio ? <TerminalRounded fontSize="small" /> : <HttpIcon fontSize="small" />}
              color={isStdio ? "secondary" : "primary"}
              variant="outlined"
              sx={{ textTransform: "uppercase", fontWeight: 600 }}
            />
            {server.auth_mode && server.auth_mode !== "no_token" ? (
              <Chip
                size="small"
                label={t("mcpHub.auth.present", "Auth configured")}
                icon={<VerifiedUserIcon fontSize="small" />}
                color="info"
                variant="outlined"
              />
            ) : (
              <Chip
                size="small"
                label={t("mcpHub.auth.none", "No auth")}
                variant="outlined"
              />
            )}
          </Stack>

          <Typography variant="body2" color="text.secondary">
            {server.description ? t(server.description) : server.id}
          </Typography>

          <Stack spacing={0.5} sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {isStdio ? t("mcpHub.fields.command") : t("mcpHub.fields.url")}
            </Typography>
            <Typography
              variant="body2"
              sx={{
                fontFamily: theme.typography.fontFamily || "monospace",
                px: 1,
                py: 0.75,
                borderRadius: 1,
                bgcolor: theme.palette.action.hover,
              }}
            >
              {connectionDetail}
            </Typography>
          </Stack>

          <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 1 }}>
            {onToggleEnabled && (
              <IconButton
                size="small"
                onClick={() => onToggleEnabled(server)}
                disabled={!canEdit}
                sx={{ color: "text.secondary" }}
              >
                <PowerSettingsNewIcon fontSize="small" />
              </IconButton>
            )}
            <IconButton size="small" onClick={() => onEdit(server)} disabled={!canEdit}>
              <EditIcon fontSize="small" />
            </IconButton>
            <IconButton
              size="small"
              onClick={() => onDelete(server)}
              disabled={!canDelete}
              sx={{ color: "text.secondary" }}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}
