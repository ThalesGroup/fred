// src/pages/AgentHub.tsx
// Copyright Thales 2025

import {
  Box,
  Typography,
  useTheme,
  Button,
  Chip,
  Fade,
  Tabs,
  Tab,
  Card,
  CardContent,
  ListItemIcon,
} from "@mui/material";
import { useState, useEffect, SyntheticEvent, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import SearchIcon from "@mui/icons-material/Search";
import FilterListIcon from "@mui/icons-material/FilterList";
import StarIcon from "@mui/icons-material/Star";
import AddIcon from "@mui/icons-material/Add";

import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import Grid2 from "@mui/material/Grid2";
import { LoadingSpinner } from "../utils/loadingSpinner";
import { TopBar } from "../common/TopBar";
import { AgentCard } from "../components/agentHub/AgentCard";

// Editor pieces
import { AgentEditDrawer } from "../components/agentHub/AgentEditDrawer";
import { CrewEditor } from "../components/agentHub/CrewEditor";

// OpenAPI
import {
  useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useDeleteAgentAgenticV1AgentsNameDeleteMutation,
  Leader,
} from "../slices/agentic/agenticOpenApi";

// UI union facade
import { AnyAgent, isLeader } from "../common/agent";
import { useAgentUpdater } from "../hooks/useAgentUpdater";
import { CreateAgentModal } from "../components/agentHub/CreateAgentModal";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";

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

  const [triggerGetFlows, { isFetching }] = useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();
  const { updateEnabled } = useAgentUpdater();

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
                      <ActionButton icon={<AddIcon />} onClick={handleOpenCreateAgent}>
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
                                onToggleFavorite={toggleFavorite}
                                onEdit={handleEdit}
                                onToggleEnabled={handleToggleEnabled}
                                onManageCrew={isLeader(agent) ? handleManageCrew : undefined}
                                onDelete={handleDeleteAgent}
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
