// Copyright Thales 2025

import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import SearchIcon from "@mui/icons-material/Search";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Fade,
  FormControl,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
  useTheme,
} from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { TopBar } from "../common/TopBar";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";
import { McpServerCard } from "../components/mcpHub/McpServerCard";
import { McpServerForm } from "../components/mcpHub/McpServerForm";
import { useToast } from "../components/ToastProvider";
import { usePermissions } from "../security/usePermissions";
import {
  McpServerConfiguration,
  useCreateMcpServerAgenticV1McpServersPostMutation,
  useDeleteMcpServerAgenticV1McpServersServerIdDeleteMutation,
  useListMcpServersAgenticV1McpServersGetQuery,
  useRestoreMcpServersFromConfigAgenticV1McpServersRestorePostMutation,
  useUpdateMcpServerAgenticV1McpServersServerIdPutMutation,
} from "../slices/agentic/agenticOpenApi";
import { LoadingSpinner } from "../utils/loadingSpinner";

const normalizeTransport = (server: McpServerConfiguration) =>
  (server.transport || "streamable_http").toLowerCase();

const sourceKindForServer = (server: McpServerConfiguration) =>
  normalizeTransport(server) === "inprocess" ? "local" : "mcp";

export const McpHub = () => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { can } = usePermissions();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { showError, showSuccess } = useToast();

  const canEdit = can("agents", "update");
  const canDelete = can("agents", "delete");

  const { data: servers, isFetching, refetch } = useListMcpServersAgenticV1McpServersGetQuery();
  const [createServer] = useCreateMcpServerAgenticV1McpServersPostMutation();
  const [updateServer] = useUpdateMcpServerAgenticV1McpServersServerIdPutMutation();
  const [deleteServer] = useDeleteMcpServerAgenticV1McpServersServerIdDeleteMutation();
  const [restoreServers, { isLoading: isRestoring }] =
    useRestoreMcpServersFromConfigAgenticV1McpServersRestorePostMutation();

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<McpServerConfiguration | null>(null);
  const [showElements, setShowElements] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<"all" | "mcp" | "local">("all");
  const [transportFilter, setTransportFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "enabled" | "disabled">("all");

  const sortedServers = useMemo(
    () =>
      [...(servers || [])].sort((a, b) => {
        return a.id.localeCompare(b.id);
      }),
    [servers],
  );

  const transportCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    sortedServers.forEach((s) => {
      const key = normalizeTransport(s);
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [sortedServers]);

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = { mcp: 0, local: 0 };
    sortedServers.forEach((s) => {
      const key = sourceKindForServer(s);
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [sortedServers]);

  const availableTransports = useMemo(
    () => Array.from(new Set(sortedServers.map((s) => normalizeTransport(s)))).sort(),
    [sortedServers],
  );

  const filteredServers = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return sortedServers.filter((server) => {
      const transport = normalizeTransport(server);
      const sourceKind = sourceKindForServer(server);
      const enabled = server.enabled !== false;

      if (sourceFilter !== "all" && sourceKind !== sourceFilter) return false;
      if (transportFilter !== "all" && transport !== transportFilter) return false;
      if (statusFilter === "enabled" && !enabled) return false;
      if (statusFilter === "disabled" && enabled) return false;

      if (!q) return true;

      const searchHaystack = [
        server.id,
        server.name,
        t(server.name),
        server.description || "",
        server.description ? t(server.description) : "",
        server.url || "",
        server.command || "",
        server.provider || "",
        ...(server.args || []),
      ]
        .join(" ")
        .toLowerCase();

      return searchHaystack.includes(q);
    });
  }, [sortedServers, searchQuery, sourceFilter, transportFilter, statusFilter, t]);

  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    sourceFilter !== "all" ||
    transportFilter !== "all" ||
    statusFilter !== "all";

  useEffect(() => {
    setShowElements(true);
  }, []);

  const handleCreate = () => {
    setEditing(null);
    setEditorOpen(true);
  };

  const handleEdit = (server: McpServerConfiguration) => {
    setEditing(server);
    setEditorOpen(true);
  };

  const handleSave = async (server: McpServerConfiguration) => {
    const safeDetail = (err: any) => {
      const raw = err?.data?.detail || err?.data || err?.message || err;
      return typeof raw === "string" ? raw : JSON.stringify(raw);
    };
    const previousId = editing?.id;
    const idChanged = Boolean(previousId && previousId !== server.id);
    try {
      if (editing) {
        await updateServer({
          serverId: server.id,
          saveMcpServerRequest: { server },
        }).unwrap();
        if (idChanged && previousId) {
          await deleteServer({ serverId: previousId }).unwrap();
        }
        showSuccess({ summary: t("mcpHub.toasts.updated") });
      } else {
        await createServer({ saveMcpServerRequest: { server } }).unwrap();
        showSuccess({ summary: t("mcpHub.toasts.created") });
      }
      setEditorOpen(false);
      setEditing(null);
      refetch();
    } catch (error: any) {
      showError({ summary: t("mcpHub.toasts.error"), detail: safeDetail(error) });
    }
  };

  const handleDelete = useCallback(
    (server: McpServerConfiguration) => {
      showConfirmationDialog({
        title: t("mcpHub.confirmDeleteTitle") || "Delete MCP server?",
        message:
          t("mcpHub.confirmDeleteMessage", { id: server.id }) ||
          `Are you sure you want to delete the MCP server “${server.id}”?`,
        onConfirm: async () => {
          try {
            await deleteServer({ serverId: server.id }).unwrap();
            showSuccess({ summary: t("mcpHub.toasts.deleted") });
            refetch();
          } catch (error: any) {
            const detail = error?.data?.detail || error?.data || error?.message || "Unknown error";
            showError({ summary: t("mcpHub.toasts.error"), detail });
          }
        },
      });
    },
    [deleteServer, refetch, showConfirmationDialog, showError, showSuccess, t],
  );

  const handleToggleEnabled = async (server: McpServerConfiguration) => {
    const safeDetail = (err: any) => {
      const raw = err?.data?.detail || err?.data || err?.message || err;
      return typeof raw === "string" ? raw : JSON.stringify(raw);
    };
    try {
      await updateServer({
        serverId: server.id,
        saveMcpServerRequest: {
          server: { ...server, enabled: server.enabled === false ? true : false },
        },
      }).unwrap();
      showSuccess({
        summary:
          server.enabled === false ? t("mcpHub.toasts.enabled") : t("mcpHub.toasts.disabled"),
      });
      refetch();
    } catch (error: any) {
      showError({ summary: t("mcpHub.toasts.error"), detail: safeDetail(error) });
    }
  };

  const handleRestore = () => {
    showConfirmationDialog({
      title: t("mcpHub.confirmRestoreTitle") || "Restore MCP servers from configuration?",
      message:
        t("mcpHub.confirmRestoreMessage") ||
        "This will overwrite any MCP server changes saved in the UI with the YAML configuration. You will lose those changes. This cannot be undone.",
      onConfirm: async () => {
        try {
          await restoreServers().unwrap();
          showSuccess({ summary: t("mcpHub.toasts.restored") });
          refetch();
        } catch (error: any) {
          const raw = error?.data?.detail || error?.data || error?.message || "Unknown error";
          showError({ summary: t("mcpHub.toasts.error"), detail: raw });
        }
      },
    });
  };

  const resetFilters = () => {
    setSearchQuery("");
    setSourceFilter("all");
    setTransportFilter("all");
    setStatusFilter("all");
  };

  return (
    <Box>
      <TopBar title={t("mcpHub.title")} description={t("mcpHub.subtitle")} />

      <Box
        sx={{
          width: "100%",
          maxWidth: 1280,
          mx: "auto",
          px: { xs: 2, md: 3 },
          pt: { xs: 3, md: 4 },
          pb: { xs: 4, md: 6 },
        }}
      >
        <Fade in={showElements} timeout={900}>
          <Card
            variant="outlined"
            sx={{
              borderRadius: 2,
              bgcolor: "transparent",
              boxShadow: "none",
              borderColor: "divider",
              mb: 2,
            }}
          >
            <CardContent sx={{ py: 1.5, px: { xs: 1.5, md: 2 } }}>
              <Stack spacing={1.5}>
                <Stack
                  direction={{ xs: "column", md: "row" }}
                  justifyContent="space-between"
                  gap={2}
                  alignItems={{ xs: "stretch", md: "center" }}
                >
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="subtitle2" sx={{ mr: 0.5 }}>
                      {t("mcpHub.title")}
                    </Typography>
                    <Chip
                      label={`${sortedServers.length} ${t("mcpHub.countLabel")}`}
                      color="primary"
                      variant="outlined"
                      size="small"
                    />
                    <Chip
                      label={`${t("mcpHub.source.mcp", "MCP")}: ${sourceCounts.mcp || 0}`}
                      size="small"
                      sx={{ borderRadius: 1 }}
                    />
                    <Chip
                      label={`${t("mcpHub.source.local", "Local")}: ${sourceCounts.local || 0}`}
                      size="small"
                      sx={{ borderRadius: 1 }}
                    />
                    {Object.entries(transportCounts).map(([transport, count]) => (
                      <Chip
                        key={transport}
                        label={`${t(`mcpHub.transport.${transport}`, transport)}: ${count}`}
                        size="small"
                        sx={{ borderRadius: 1 }}
                      />
                    ))}
                    {hasActiveFilters && (
                      <Chip
                        label={`${filteredServers.length} ${t("mcpHub.resultsLabel", "results")}`}
                        size="small"
                        color="secondary"
                        variant="outlined"
                        sx={{ borderRadius: 1 }}
                      />
                    )}
                  </Stack>

                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<RefreshIcon />}
                      onClick={canEdit ? handleRestore : undefined}
                      disabled={!canEdit || isRestoring}
                      sx={{ textTransform: "none" }}
                    >
                      {t("mcpHub.restoreButton")}
                    </Button>
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<AddIcon />}
                      onClick={canEdit ? handleCreate : undefined}
                      disabled={!canEdit}
                      sx={{ textTransform: "none" }}
                    >
                      {t("mcpHub.addButton")}
                    </Button>
                  </Stack>
                </Stack>

                <Stack
                  direction={{ xs: "column", lg: "row" }}
                  spacing={1.25}
                  alignItems={{ xs: "stretch", lg: "center" }}
                >
                  <TextField
                    size="small"
                    fullWidth
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t(
                      "mcpHub.searchPlaceholder",
                      "Search by id, name, description, URL, command, or provider",
                    )}
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <SearchIcon fontSize="small" />
                        </InputAdornment>
                      ),
                    }}
                    sx={{ flex: 1.2 }}
                  />

                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25} sx={{ flex: 1 }}>
                    <FormControl size="small" sx={{ minWidth: 150, flex: 1 }}>
                      <InputLabel id="mcp-source-filter-label">
                        {t("mcpHub.filters.source", "Source")}
                      </InputLabel>
                      <Select
                        labelId="mcp-source-filter-label"
                        label={t("mcpHub.filters.source", "Source")}
                        value={sourceFilter}
                        onChange={(e) => setSourceFilter(e.target.value as "all" | "mcp" | "local")}
                      >
                        <MenuItem value="all">{t("mcpHub.filters.all", "All")}</MenuItem>
                        <MenuItem value="mcp">{t("mcpHub.source.mcp", "MCP")}</MenuItem>
                        <MenuItem value="local">{t("mcpHub.source.local", "Local")}</MenuItem>
                      </Select>
                    </FormControl>

                    <FormControl size="small" sx={{ minWidth: 170, flex: 1 }}>
                      <InputLabel id="mcp-transport-filter-label">
                        {t("mcpHub.filters.transport", "Transport")}
                      </InputLabel>
                      <Select
                        labelId="mcp-transport-filter-label"
                        label={t("mcpHub.filters.transport", "Transport")}
                        value={transportFilter}
                        onChange={(e) => setTransportFilter(e.target.value)}
                      >
                        <MenuItem value="all">{t("mcpHub.filters.all", "All")}</MenuItem>
                        {availableTransports.map((transport) => (
                          <MenuItem key={transport} value={transport}>
                            {t(`mcpHub.transport.${transport}`, transport)}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl size="small" sx={{ minWidth: 150, flex: 1 }}>
                      <InputLabel id="mcp-status-filter-label">
                        {t("mcpHub.filters.status", "Status")}
                      </InputLabel>
                      <Select
                        labelId="mcp-status-filter-label"
                        label={t("mcpHub.filters.status", "Status")}
                        value={statusFilter}
                        onChange={(e) =>
                          setStatusFilter(e.target.value as "all" | "enabled" | "disabled")
                        }
                      >
                        <MenuItem value="all">{t("mcpHub.filters.all", "All")}</MenuItem>
                        <MenuItem value="enabled">{t("mcpHub.filters.enabled", "Enabled")}</MenuItem>
                        <MenuItem value="disabled">{t("mcpHub.filters.disabled", "Disabled")}</MenuItem>
                      </Select>
                    </FormControl>
                  </Stack>

                  <Button
                    size="small"
                    variant="outlined"
                    onClick={resetFilters}
                    disabled={!hasActiveFilters}
                    sx={{ textTransform: "none", minWidth: 110 }}
                  >
                    {t("mcpHub.clearFilters", "Reset")}
                  </Button>
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        </Fade>

        <Fade in={showElements} timeout={1100}>
          <Card
            variant="outlined"
            sx={{
              borderRadius: 2,
              bgcolor: "transparent",
              boxShadow: "none",
              borderColor: "divider",
            }}
          >
            <CardContent sx={{ p: { xs: 2, md: 3 } }}>
              {isFetching ? (
                <Box display="flex" justifyContent="center" alignItems="center" minHeight="360px">
                  <LoadingSpinner />
                </Box>
              ) : sortedServers.length === 0 ? (
                <Box
                  sx={{
                    border: `1px dashed ${theme.palette.divider}`,
                    borderRadius: 2,
                    p: 4,
                    textAlign: "center",
                  }}
                >
                  <Typography variant="subtitle1">{t("mcpHub.emptyTitle")}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    {t("mcpHub.emptyHint")}
                  </Typography>
                  <Button
                    startIcon={<AddIcon />}
                    sx={{ mt: 2 }}
                    variant="outlined"
                    onClick={handleCreate}
                    disabled={!canEdit}
                  >
                    {t("mcpHub.addButton")}
                  </Button>
                </Box>
              ) : filteredServers.length === 0 ? (
                <Box
                  sx={{
                    border: `1px dashed ${theme.palette.divider}`,
                    borderRadius: 2,
                    p: 4,
                    textAlign: "center",
                  }}
                >
                  <Typography variant="subtitle1">{t("mcpHub.noResultsTitle", "No connector matches your search")}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    {t("mcpHub.noResultsHint", "Try removing filters or broadening the search.")}
                  </Typography>
                  <Button
                    sx={{ mt: 2 }}
                    variant="outlined"
                    onClick={resetFilters}
                    disabled={!hasActiveFilters}
                  >
                    {t("mcpHub.clearFilters", "Reset")}
                  </Button>
                </Box>
              ) : (
                <Grid2 container spacing={2}>
                  {filteredServers.map((server) => (
                    <Grid2
                      key={server.id}
                      size={{ xs: 12, sm: 12, md: 6, lg: 6 }}
                      display="flex"
                    >
                      <Fade in timeout={500}>
                        <Box sx={{ width: "100%" }}>
                          <McpServerCard
                            server={server}
                            onEdit={handleEdit}
                            onDelete={handleDelete}
                            canEdit={canEdit}
                            canDelete={canDelete}
                            onToggleEnabled={canEdit ? handleToggleEnabled : undefined}
                          />
                        </Box>
                      </Fade>
                    </Grid2>
                  ))}
                </Grid2>
              )}
            </CardContent>
          </Card>
        </Fade>
      </Box>

      <McpServerForm
        open={editorOpen}
        initial={editing}
        onCancel={() => {
          setEditorOpen(false);
          setEditing(null);
        }}
        onSubmit={handleSave}
      />
    </Box>
  );
};
