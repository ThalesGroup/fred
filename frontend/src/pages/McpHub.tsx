// Copyright Thales 2025

import AddIcon from "@mui/icons-material/Add";
import FilterListIcon from "@mui/icons-material/FilterList";
import SearchIcon from "@mui/icons-material/Search";
import { Box, Button, Card, CardContent, Chip, Fade, Stack, Typography, useTheme } from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { TopBar } from "../common/TopBar";
import { McpServerCard } from "../components/mcpHub/McpServerCard";
import { McpServerForm } from "../components/mcpHub/McpServerForm";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";
import { useToast } from "../components/ToastProvider";
import { usePermissions } from "../security/usePermissions";
import {
  McpServerConfiguration,
  useCreateMcpServerAgenticV1McpServersPostMutation,
  useDeleteMcpServerAgenticV1McpServersServerIdDeleteMutation,
  useListMcpServersAgenticV1McpServersGetQuery,
  useUpdateMcpServerAgenticV1McpServersServerIdPutMutation,
} from "../slices/agentic/agenticOpenApi";
import { LoadingSpinner } from "../utils/loadingSpinner";

const ActionButton = ({
  icon,
  children,
  ...props
}: {
  icon: ReactNode;
  children: ReactNode;
} & React.ComponentProps<typeof Button>) => {
  const theme = useTheme();
  return (
    <Button
      startIcon={<Box component="span" sx={{ color: "inherit", display: "flex" }}>{icon}</Box>}
      size="small"
      {...props}
      sx={{
        borderRadius: 1.5,
        textTransform: "none",
        px: 1.25,
        height: 32,
        border: `1px solid ${theme.palette.divider}`,
        bgcolor: "transparent",
        color: "text.primary",
        "&:hover": {
          borderColor: theme.palette.primary.main,
          backgroundColor: theme.palette.mode === "dark" ? "rgba(25,118,210,0.10)" : "rgba(25,118,210,0.06)",
        },
        ...props.sx,
      }}
    >
      {children}
    </Button>
  );
};

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

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<McpServerConfiguration | null>(null);
  const [showElements, setShowElements] = useState(false);

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
      const key = (s.transport || "streamable_http").toLowerCase();
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [sortedServers]);

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
    try {
      if (editing) {
        await updateServer({
          serverId: editing.id,
          saveMcpServerRequest: { server },
        }).unwrap();
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

  const handleDelete = (server: McpServerConfiguration) => {
    showConfirmationDialog({
      title: t("mcpHub.confirmDeleteTitle"),
      message: t("mcpHub.confirmDeleteMessage", { id: server.id }),
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
  };

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
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" gap={2} alignItems="center">
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                  <Chip
                    label={`${sortedServers.length} ${t("mcpHub.countLabel")}`}
                    color="primary"
                    variant="outlined"
                    size="small"
                  />
                  {Object.entries(transportCounts).map(([transport, count]) => (
                    <Chip
                      key={transport}
                      label={`${t(`mcpHub.transport.${transport}`, transport)}: ${count}`}
                      size="small"
                      sx={{ borderRadius: 1 }}
                    />
                  ))}
                </Stack>
                <Box display="flex" gap={1}>
                  <ActionButton icon={<SearchIcon />}>{t("mcpHub.search")}</ActionButton>
                  <ActionButton icon={<FilterListIcon />}>{t("mcpHub.filter")}</ActionButton>
                  <ActionButton icon={<AddIcon />} onClick={canEdit ? handleCreate : undefined} disabled={!canEdit}>
                    {t("mcpHub.addButton")}
                  </ActionButton>
                </Box>
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
              ) : (
                <Grid2 container spacing={2}>
                  {sortedServers.map((server) => (
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
