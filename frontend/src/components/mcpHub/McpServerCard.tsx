// Copyright Thales 2025

import EditIcon from "@mui/icons-material/Edit";
import HttpIcon from "@mui/icons-material/Http";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import TerminalRounded from "@mui/icons-material/TerminalRounded";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import { Box, CardContent, Divider, IconButton, Stack, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
import { CatalogBadge } from "../../shared/ui/catalog/CatalogBadge";
import { CatalogCard } from "../../shared/ui/catalog/CatalogCard";
import { CatalogMetaRow } from "../../shared/ui/catalog/CatalogMetaRow";
import { McpServerConfiguration } from "../../slices/agentic/agenticOpenApi";
import { DeleteIconButton } from "../../shared/ui/buttons/DeleteIconButton";

export interface McpServerCardProps {
  server: McpServerConfiguration;
  onEdit: (server: McpServerConfiguration) => void;
  onDelete: (server: McpServerConfiguration) => void;
  canEdit: boolean;
  canDelete: boolean;
  onToggleEnabled?: (server: McpServerConfiguration) => void;
}

export function McpServerCard({ server, onEdit, onDelete, canEdit, canDelete, onToggleEnabled }: McpServerCardProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const transport = (server.transport || "streamable_http").toLowerCase();
  const isInprocess = transport === "inprocess";
  const isStdio = transport === "stdio";
  const sourceKind = isInprocess ? "local" : "mcp";
  const isEnabled = server.enabled !== false;
  const connectionDetail = isInprocess
    ? server.provider || "—"
    : isStdio
      ? [server.command, ...(server.args || [])].filter(Boolean).join(" ") || "—"
      : server.url || "—";
  const transportIcon = sourceKind === "local" ? <TerminalRounded fontSize="small" /> : <HttpIcon fontSize="small" />;
  const sourceLabel = t(`mcpHub.source.${sourceKind}`, sourceKind === "local" ? "Local" : "MCP");
  const transportLabel = t(`mcpHub.transport.${transport}`, transport);
  const authModeLabel = server.auth_mode
    ? t(`mcpHub.auth.${server.auth_mode}`, server.auth_mode)
    : t("mcpHub.auth.none", "No auth");
  const primaryDetailLabel = isInprocess
    ? t("mcpHub.fields.provider", "Provider")
    : isStdio
      ? t("mcpHub.fields.command")
      : t("mcpHub.fields.url");

  return (
    <CatalogCard disabledTone={!isEnabled}>
      <CardContent>
        <Stack spacing={1.25} sx={{ minHeight: 250 }}>
          <Stack direction="row" spacing={1} alignItems="flex-start">
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography
                  variant="subtitle1"
                  sx={{ fontWeight: 700, lineHeight: 1.2, minWidth: 0 }}
                  title={server.id}
                >
                  {t(server.name)}
                </Typography>
                <CatalogBadge
                  label={isEnabled ? t("mcpHub.status.enabled") : t("mcpHub.status.disabled")}
                  tone={isEnabled ? "success" : "warning"}
                />
              </Stack>
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                  mt: 0.5,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  minHeight: "2.7em",
                }}
                title={server.description ? t(server.description) : undefined}
              >
                {server.description ? t(server.description) : t("mcpHub.emptyHint")}
              </Typography>
            </Box>

            <Stack direction="row" spacing={0.25} sx={{ ml: "auto" }}>
              {onToggleEnabled && (
                <SimpleTooltip title={isEnabled ? t("mcpHub.toasts.disabled") : t("mcpHub.toasts.enabled")}>
                  <span>
                    <IconButton
                      size="small"
                      onClick={() => onToggleEnabled(server)}
                      disabled={!canEdit}
                      sx={{ color: "text.secondary" }}
                    >
                      <PowerSettingsNewIcon fontSize="small" />
                    </IconButton>
                  </span>
                </SimpleTooltip>
              )}
              <SimpleTooltip title={t("common.edit", "Edit")}>
                <span>
                  <IconButton size="small" onClick={() => onEdit(server)} disabled={!canEdit}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                </span>
              </SimpleTooltip>
              <SimpleTooltip title={t("common.delete", "Delete")}>
                <span>
                  <DeleteIconButton size="small" onClick={() => onDelete(server)} disabled={!canDelete} />
                </span>
              </SimpleTooltip>
            </Stack>
          </Stack>

          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
            <CatalogBadge
              label={sourceLabel}
              icon={transportIcon}
              tone={sourceKind === "local" ? "secondary" : "primary"}
            />
            <CatalogBadge label={transportLabel} />
            {!isInprocess && (
              <CatalogBadge
                label={authModeLabel}
                icon={
                  server.auth_mode && server.auth_mode !== "no_token" ? (
                    <VerifiedUserIcon fontSize="small" />
                  ) : undefined
                }
                tone={server.auth_mode && server.auth_mode !== "no_token" ? "info" : "neutral"}
              />
            )}
          </Stack>

          <Divider />

          <Stack spacing={0.9} sx={{ flex: 1 }}>
            <CatalogMetaRow
              label={t("mcpHub.fields.id")}
              value={
                <Box
                  component="span"
                  sx={{
                    display: "inline-block",
                    px: 0.75,
                    py: 0.25,
                    borderRadius: 1,
                    bgcolor: "action.hover",
                    fontFamily: "'JetBrains Mono', 'Fira Code', 'Menlo', 'Roboto Mono', monospace",
                    fontSize: "0.82rem",
                    whiteSpace: "nowrap",
                    maxWidth: "100%",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    verticalAlign: "middle",
                  }}
                  title={server.id}
                >
                  {server.id}
                </Box>
              }
            />

            <CatalogMetaRow
              label={primaryDetailLabel}
              value={
                <Box
                  component="span"
                  sx={{
                    display: "inline-block",
                    width: "100%",
                    px: 0.75,
                    py: 0.5,
                    borderRadius: 1,
                    bgcolor: theme.palette.action.hover,
                    fontFamily: isInprocess
                      ? theme.typography.fontFamily
                      : "'JetBrains Mono', 'Fira Code', 'Menlo', 'Roboto Mono', monospace",
                    fontSize: "0.83rem",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                  title={connectionDetail}
                >
                  {connectionDetail}
                </Box>
              }
            />

            {!isInprocess && <CatalogMetaRow label={t("mcpHub.fields.auth_mode")} value={authModeLabel} />}
          </Stack>
        </Stack>
      </CardContent>
    </CatalogCard>
  );
}
