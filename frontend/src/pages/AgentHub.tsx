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
import { useState, useEffect, SyntheticEvent, useMemo } from "react";
import { useTranslation } from "react-i18next";
import SearchIcon from "@mui/icons-material/Search";
import AddIcon from "@mui/icons-material/Add";
import FilterListIcon from "@mui/icons-material/FilterList";
import StarIcon from "@mui/icons-material/Star";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import Grid2 from "@mui/material/Grid2";
import { LoadingSpinner } from "../utils/loadingSpinner";
import { TopBar } from "../common/TopBar";
import { AgentCard } from "../components/agentHub/AgentCard";
import { CreateAgentModal } from "../components/agentHub/CreateAgentModal";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";

// OpenAPI
import {
  AgenticFlow,
  GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse,
  useDeleteAgentAgenticV1AgentsNameDeleteMutation,
  useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
} from "../slices/agentic/agenticOpenApi";

interface AgentCategory {
  name: string;
  isTag?: boolean;
}

const extractUniqueTags = (agents: AgenticFlow[]): string[] =>
  agents
    .map((a) => a.tag || "")
    .filter((t) => t && t.trim() !== "")
    .filter((tag, idx, self) => self.indexOf(tag) === idx);

const mapFlowsToAgents = (flows: GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse): AgenticFlow[] =>
  (flows || []).map((f) => ({
    name: f.name,
    role: f.role,
    nickname: f.nickname ?? undefined,
    description: f.description,
    icon: f.icon ?? undefined,
    experts: f.experts ?? undefined,
    tag: f.tag ?? undefined,
    // keep .tags for legacy code reading it
    tags: f.tag ?? undefined,
  })) as AgenticFlow[];

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

  const [agenticFlows, setAgenticFlows] = useState<AgenticFlow[]>([]);
  const [tabValue, setTabValue] = useState(0);
  const [showElements, setShowElements] = useState(false);
  const [favoriteAgents, setFavoriteAgents] = useState<string[]>([]);
  const [categories, setCategories] = useState<AgentCategory[]>([{ name: "all" }, { name: "favorites" }]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const handleOpenCreateAgent = () => setIsCreateModalOpen(true);
  const handleCloseCreateAgent = () => setIsCreateModalOpen(false);

  const [triggerGetFlows, { isFetching }] = useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();
  const [deleteAgent] = useDeleteAgentAgenticV1AgentsNameDeleteMutation();
  const { showConfirmationDialog } = useConfirmationDialog();

  const handleDeleteAgent = (name: string) => {
    showConfirmationDialog({
      title: t("agentHub.confirmDeleteTitle"),
      message: t("agentHub.confirmDeleteMessage"),
      onConfirm: async () => {
        try {
          await deleteAgent({ name }).unwrap();
          fetchAgents();
        } catch (err) {
          console.error("Failed to delete agent:", err);
        }
      },
    });
  };

  const fetchAgents = async () => {
    try {
      const flows = await triggerGetFlows().unwrap();
      const mapped = mapFlowsToAgents(flows);
      setAgenticFlows(mapped);

      const tags = extractUniqueTags(mapped);
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
    if (tabValue === 0) return agenticFlows;
    if (tabValue === 1) return agenticFlows.filter((a) => favoriteAgents.includes(a.name));
    if (categories.length > 2 && tabValue >= 2) {
      const tagName = categories[tabValue].name;
      return agenticFlows.filter((a) => a.tag === tagName);
    }
    return agenticFlows;
  }, [tabValue, agenticFlows, favoriteAgents, categories]);

  const toggleFavorite = (agentName: string) => {
    const updated = favoriteAgents.includes(agentName)
      ? favoriteAgents.filter((n) => n !== agentName)
      : [...favoriteAgents, agentName];
    setFavoriteAgents(updated);
    localStorage.setItem("favoriteAgents", JSON.stringify(updated));
  };

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
                  const isTag = !!category.isTag;
                  const count = isFav
                    ? favoriteAgents.length
                    : isTag
                      ? agenticFlows.filter((a) => a.tag === category.name).length
                      : agenticFlows.length;

                  return (
                    <Tab
                      key={`${category.name}-${index}`}
                      label={
                        <Box sx={{ display: "flex", alignItems: "center" }}>
                          {isFav && <StarIcon fontSize="small" sx={{ mr: 0.5, color: "warning.main" }} />}
                          {isTag && <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, color: "text.secondary" }} />}
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
                      {tabValue >= 2 && categories[tabValue]?.isTag && (
                        <LocalOfferIcon fontSize="small" sx={{ color: "text.secondary" }} />
                      )}
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
                            <Box>
                              <AgentCard
                                agent={agent}
                                onDelete={handleDeleteAgent}
                                isFavorite={favoriteAgents.includes(agent.name)}
                                onToggleFavorite={toggleFavorite}
                                allAgents={agenticFlows}
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

                  {/* Create modal */}
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
      </Box>
    </>
  );
};
