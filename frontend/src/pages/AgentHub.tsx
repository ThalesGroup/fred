// src/pages/AgentHub.tsx
// Copyright Thales 2025

import Editor from "@monaco-editor/react";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import FilterListIcon from "@mui/icons-material/FilterList";
import SearchIcon from "@mui/icons-material/Search";
import StarIcon from "@mui/icons-material/Star";

import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Drawer,
  Fade,
  IconButton,
  ListItemIcon,
  Tab,
  Tabs,
  Typography,
  useTheme,
} from "@mui/material";
import { SyntheticEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { usePermissions } from "../security/usePermissions";

import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import Grid2 from "@mui/material/Grid2";
import { TopBar } from "../common/TopBar";
import { AgentCard } from "../components/agentHub/AgentCard";
import { LoadingSpinner } from "../utils/loadingSpinner";

// Editor pieces
import { AgentEditDrawer } from "../components/agentHub/AgentEditDrawer";
import { CrewEditor } from "../components/agentHub/CrewEditor";

// OpenAPI
import {
  Leader,
  useDeleteAgentAgenticV1AgentsNameDeleteMutation,
  useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
} from "../slices/agentic/agenticOpenApi";

// UI union facade
import { AnyAgent, isLeader } from "../common/agent";
import { AgentAssetManagerDrawer } from "../components/agentHub/AgentAssetManagerDrawer";
import { CreateAgentModal } from "../components/agentHub/CreateAgentModal";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";
import { useToast } from "../components/ToastProvider";
import { useAgentUpdater } from "../hooks/useAgentUpdater";
import { useLazyGetRuntimeSourceTextQuery } from "../slices/agentic/agenticSourceApi";

type AgentCategory = { name: string; isTag?: boolean };

const ActionButton = ({
  icon,
  children,
  ...props
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
} & React.ComponentProps<typeof Button>) => {
  const theme = useTheme();
  return (
    <Button
      startIcon={<ListItemIcon sx={{ minWidth: 0, mr: 0.75, color: "inherit" }}>{icon}</ListItemIcon>}
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

export const AgentHub = () => {
  const theme = useTheme();
  const { t } = useTranslation();
  const { showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const [agents, setAgents] = useState<AnyAgent[]>([]);
  const [tabValue, setTabValue] = useState(0);
  const [showElements, setShowElements] = useState(false);
  const [favoriteAgents, setFavoriteAgents] = useState<string[]>([]);
  const [categories, setCategories] = useState<AgentCategory[]>([{ name: "all" }, { name: "favorites" }]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  // drawers / selection
  const [selected, setSelected] = useState<AnyAgent | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [crewOpen, setCrewOpen] = useState(false);
  const [triggerDeleteAgent] = useDeleteAgentAgenticV1AgentsNameDeleteMutation();

  const handleOpenCreateAgent = () => setIsCreateModalOpen(true);
  const handleCloseCreateAgent = () => setIsCreateModalOpen(false);

  const [assetManagerOpen, setAssetManagerOpen] = useState(false);
  const [agentForAssetManagement, setAgentForAssetManagement] = useState<AnyAgent | null>(null);

  const [triggerGetFlows, { isFetching }] = useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();
  const { updateEnabled } = useAgentUpdater();
  const [triggerGetSource] = useLazyGetRuntimeSourceTextQuery();

  // RBAC utils
  const { can } = usePermissions();
  const canEditAgents = can("agents", "update");
  const canCreateAgents = can("agents", "create");
  const canDeleteAgents = can("agents", "delete");
  const [codeDrawer, setCodeDrawer] = useState<{
    open: boolean;
    title: string;
    content: string | null;
  }>({ open: false, title: "", content: null });

  const handleCloseCodeDrawer = () => {
    setCodeDrawer({ open: false, title: "", content: null });
  };

  const handleInspectCode = async (agent: AnyAgent) => {
    const AGENT_CODE_KEY = `agent.${agent.name}`;

    // 1. Set loading state and open the drawer immediately
    // 👇 CHANGE: Use setCodeDrawer instead of setCodeViewer
    setCodeDrawer({ open: true, title: `Fetching Source: ${agent.name}...`, content: null });

    try {
      // 2. Trigger the lazy query and unwrap the promise for the result
      // The request parameter is 'key' (for /by-object?key=...)
      const code = await triggerGetSource({ key: AGENT_CODE_KEY }).unwrap();

      // 3. Set the successful content state
      // 👇 CHANGE: Use setCodeDrawer instead of setCodeViewer
      setCodeDrawer({
        open: true,
        title: `Source: ${agent.name}`,
        content: code,
      });
    } catch (error: any) {
      console.error("Error fetching agent source:", error);
      // 👇 CHANGE: Use handleCloseCodeDrawer instead of handleCloseCodeViewer
      handleCloseCodeDrawer(); // Close the drawer

      // Extract detailed error message if possible
      const detail = error?.data || error?.message || "Check network connection or agent exposure.";

      // Assuming your showError function is available
      showError({
        summary: "Code Inspection Failed",
        detail: `Could not retrieve source for ${agent.name}. Details: ${detail}`,
      });
    }
  };

  const fetchAgents = async () => {
    try {
      const flows = (await triggerGetFlows().unwrap()) as unknown as AnyAgent[];
      setAgents(flows);

      const tags = extractUniqueTags(flows);
      setCategories([{ name: "all" }, { name: "favorites" }, ...tags.map((tag) => ({ name: tag, isTag: true }))]);

      const savedFavorites = localStorage.getItem("favoriteAgents");
      if (savedFavorites) setFavoriteAgents(JSON.parse(savedFavorites));
    } catch (err) {
      console.error("Error fetching agents:", err);
    }
  };

  useEffect(() => {
    setShowElements(true);
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTabChange = (_event: SyntheticEvent, newValue: number) => setTabValue(newValue);

  const filteredAgents = useMemo(() => {
    if (tabValue === 0) return agents;
    if (tabValue === 1) return agents.filter((a) => favoriteAgents.includes(a.name));
    if (categories.length > 2 && tabValue >= 2) {
      const tagName = categories[tabValue].name;
      return agents.filter((a) => a.tags?.includes(tagName));
    }
    return agents;
  }, [tabValue, agents, favoriteAgents, categories]);

  const toggleFavorite = (agentName: string) => {
    const updated = favoriteAgents.includes(agentName)
      ? favoriteAgents.filter((n) => n !== agentName)
      : [...favoriteAgents, agentName];
    setFavoriteAgents(updated);
    localStorage.setItem("favoriteAgents", JSON.stringify(updated));
  };

  // ---- ACTION handlers wired to card --------------------------------------

  const handleEdit = (agent: AnyAgent) => {
    setSelected(agent);
    setEditOpen(true);
  };

  const handleToggleEnabled = async (agent: AnyAgent) => {
    await updateEnabled(agent, !agent.enabled);
    fetchAgents();
  };

  const handleManageCrew = (leader: Leader & { type: "leader" }) => {
    setSelected(leader);
    setCrewOpen(true);
  };

  const handleDeleteAgent = useCallback(
    (agent: AnyAgent) => {
      showConfirmationDialog({
        title: t("agentHub.confirmDeleteTitle") || "Delete Agent?",
        message:
          t("agentHub.confirmDeleteMessage", { name: agent.name }) ||
          `Are you sure you want to delete the agent “${agent.name}”? This action cannot be undone.`,
        onConfirm: async () => {
          try {
            await triggerDeleteAgent({ name: agent.name }).unwrap();
            fetchAgents();
          } catch (err) {
            console.error("Failed to delete agent:", err);
          }
        },
      });
    },
    [showConfirmationDialog, triggerDeleteAgent, fetchAgents, t],
  );

  const handleManageAssets = (agent: AnyAgent) => {
    setAgentForAssetManagement(agent);
    setAssetManagerOpen(true);
  };

  const handleCloseAssetManager = () => {
    setAssetManagerOpen(false);
    setAgentForAssetManagement(null);
    // Optional: If asset deletion/upload should refresh the main agent list (e.g., if metadata changes), uncomment the line below.
    // fetchAgents();
  };
  // ------------------------------------------------------------------------

  const sectionTitle = useMemo(() => {
    if (tabValue === 0) return t("agentHub.allAgents");
    if (tabValue === 1) return t("agentHub.favoriteAgents");
    if (categories.length > 2 && tabValue >= 2) return `${categories[tabValue].name} ${t("agentHub.agents")}`;
    return t("agentHub.agents");
  }, [tabValue, categories, t]);

  return (
    <>
      <TopBar title={t("agentHub.title")} description={t("agentHub.description")} />

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
        {/* Header / Tabs */}
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
            <CardContent sx={{ py: 1, px: { xs: 1, md: 2 } }}>
              <Tabs
                value={tabValue}
                onChange={handleTabChange}
                variant="scrollable"
                scrollButtons="auto"
                sx={{
                  minHeight: 44,
                  "& .MuiTab-root": {
                    textTransform: "none",
                    fontSize: "0.9rem",
                    minHeight: 44,
                    minWidth: 120,
                    color: "text.secondary",
                  },
                  "& .Mui-selected": { color: "text.primary", fontWeight: 600 },
                  "& .MuiTabs-indicator": {
                    backgroundColor: theme.palette.primary.main,
                    height: 3,
                    borderRadius: 1.5,
                  },
                }}
              >
                {categories.map((category, index) => {
                  const isFav = category.name === "favorites";
                  const count = isFav
                    ? favoriteAgents.length
                    : agents.filter((a) => a.tags?.includes(category.name)).length;

                  return (
                    <Tab
                      key={`${category.name}-${index}`}
                      label={
                        <Box sx={{ display: "flex", alignItems: "center" }}>
                          {isFav && <StarIcon fontSize="small" sx={{ mr: 0.5, color: "warning.main" }} />}
                          <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, color: "text.secondary" }} />
                          <Typography variant="body2" sx={{ textTransform: "capitalize" }}>
                            {t(`agentHub.categories.${category.name}`, category.name)}
                          </Typography>
                          <Chip
                            size="small"
                            label={count}
                            sx={{
                              ml: 1,
                              height: 18,
                              fontSize: "0.7rem",
                              bgcolor: "transparent",
                              border: `1px solid ${theme.palette.divider}`,
                              color: "text.secondary",
                            }}
                          />
                        </Box>
                      }
                    />
                  );
                })}
              </Tabs>
            </CardContent>
          </Card>
        </Fade>
        {/* Content */}
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
              ) : (
                <>
                  {/* Section header */}
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                    <Box display="flex" alignItems="center" gap={1}>
                      {tabValue === 1 && <StarIcon fontSize="small" sx={{ color: "warning.main" }} />}
                      {tabValue >= 2 && <LocalOfferIcon fontSize="small" sx={{ color: "text.secondary" }} />}
                      <Typography variant="h6" fontWeight={600}>
                        {sectionTitle}{" "}
                        <Typography component="span" variant="body2" color="text.secondary">
                          ({filteredAgents.length})
                        </Typography>
                      </Typography>
                    </Box>

                    <Box sx={{ display: "flex", gap: 1 }}>
                      <ActionButton icon={<SearchIcon />}>{t("agentHub.search")}</ActionButton>
                      <ActionButton icon={<FilterListIcon />}>{t("agentHub.filter")}</ActionButton>
                      <ActionButton
                        icon={<AddIcon />}
                        onClick={canCreateAgents ? handleOpenCreateAgent : undefined}
                        disabled={!canCreateAgents}
                      >
                        {t("agentHub.create")}
                      </ActionButton>
                    </Box>
                  </Box>

                  {/* Grid */}
                  {filteredAgents.length > 0 ? (
                    <Grid2 container spacing={2}>
                      {filteredAgents.map((agent) => (
                        <Grid2 key={agent.name} size={{ xs: 12, sm: 6, md: 4, lg: 4, xl: 4 }} sx={{ display: "flex" }}>
                          <Fade in timeout={500}>
                            <Box sx={{ width: "100%" }}>
                              <AgentCard
                                agent={agent}
                                isFavorite={favoriteAgents.includes(agent.name)}
                                onToggleFavorite={canEditAgents ? toggleFavorite : undefined}
                                onEdit={canEditAgents ? handleEdit : undefined}
                                onToggleEnabled={canEditAgents ? handleToggleEnabled : undefined}
                                onManageCrew={canEditAgents && isLeader(agent) ? handleManageCrew : undefined}
                                onDelete={canDeleteAgents ? handleDeleteAgent : undefined}
                                onManageAssets={canEditAgents ? handleManageAssets : undefined}
                                onInspectCode={handleInspectCode}
                              />
                            </Box>
                          </Fade>
                        </Grid2>
                      ))}
                    </Grid2>
                  ) : (
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="center"
                      justifyContent="center"
                      minHeight="280px"
                      sx={{
                        border: `1px dashed ${theme.palette.divider}`,
                        borderRadius: 2,
                        p: 3,
                      }}
                    >
                      <Typography variant="subtitle1" color="text.secondary" align="center">
                        {t("agentHub.noAgents")}
                      </Typography>
                      {tabValue === 1 && (
                        <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 0.5 }}>
                          {t("agentHub.noFavorites")}
                        </Typography>
                      )}
                      {tabValue >= 2 && (
                        <Typography variant="body2" color="text.secondary" align="center" sx={{ mt: 0.5 }}>
                          {t("agentHub.noTag", { tag: categories[tabValue]?.name })}
                        </Typography>
                      )}
                    </Box>
                  )}

                  {/* Create modal (optional) */}
                  {isCreateModalOpen && (
                    <CreateAgentModal
                      open={isCreateModalOpen}
                      onClose={handleCloseCreateAgent}
                      onCreated={() => {
                        handleCloseCreateAgent();
                        fetchAgents();
                      }}
                    />
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </Fade>
        {/* Drawers / Modals */}
        <AgentEditDrawer open={editOpen} agent={selected} onClose={() => setEditOpen(false)} onSaved={fetchAgents} />
        <CrewEditor
          open={crewOpen}
          leader={selected && isLeader(selected) ? (selected as Leader & { type: "leader" }) : null}
          allAgents={agents}
          onClose={() => setCrewOpen(false)}
          onSaved={fetchAgents}
        />
        {agentForAssetManagement && (
          <AgentAssetManagerDrawer
            isOpen={assetManagerOpen}
            onClose={handleCloseAssetManager}
            agentId={agentForAssetManagement.name}
          />
        )}

        <Box
          component={Drawer}
          anchor="right"
          open={codeDrawer.open}
          onClose={handleCloseCodeDrawer}
          // Custom Drawer Paper styling for width
          slotProps={{
            paper: {
              // This 'paper' key targets the internal Paper component of the Drawer
              sx: {
                // Set the desired width, which remains the same as your last request
                width: { xs: "100%", sm: 600, md: 900 },
                maxWidth: "100%",
              },
            },
          }}
        >
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              height: "100%", // Ensures content fills the drawer height
            }}
          >
            {/* Drawer Header */}
            <Box
              sx={{
                p: 2,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderBottom: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {codeDrawer.title}
              </Typography>
              <IconButton onClick={handleCloseCodeDrawer} size="large">
                <CloseIcon />
              </IconButton>
            </Box>

            {/* Drawer Content - Monaco Editor */}
            <Box sx={{ flexGrow: 1, overflowY: "hidden" }}>
              {codeDrawer.content ? (
                <Editor
                  // Set height to 100% to fill the remaining space in the drawer
                  height="100%"
                  defaultLanguage="python"
                  language="python"
                  defaultValue={codeDrawer.content}
                  theme={theme.palette.mode === "dark" ? "vs-dark" : "vs-light"}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    wordWrap: "on",
                    scrollBeyondLastLine: false,
                    // Add padding inside the editor for a cleaner look
                    padding: { top: 10, bottom: 10 },
                    fontSize: 12,
                  }}
                />
              ) : (
                // Loading state
                <Box display="flex" justifyContent="center" alignItems="center" height="100%">
                  <Typography align="center" sx={{ p: 4 }}>
                    Loading agent source code...
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </>
  );
};

function extractUniqueTags(agents: AnyAgent[]): string[] {
  const tagsSet = new Set<string>();
  agents.forEach((agent) => {
    if (agent.tags && Array.isArray(agent.tags)) {
      agent.tags.forEach((tag) => {
        if (typeof tag === "string" && tag.trim() !== "") {
          tagsSet.add(tag);
        }
      });
    }
  });
  return Array.from(tagsSet);
}
