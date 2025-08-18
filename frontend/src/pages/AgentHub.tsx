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

import { Box, Typography, useTheme, Container, Paper, Button, Chip, Fade, Tabs, Tab } from "@mui/material";
import { useState, useEffect, SyntheticEvent, useMemo } from "react";
import { useTranslation } from "react-i18next";
import SearchIcon from "@mui/icons-material/Search";
import AddIcon from "@mui/icons-material/Add";
import FilterListIcon from "@mui/icons-material/FilterList";
import StarIcon from "@mui/icons-material/Star";
import Grid2 from "@mui/material/Grid2";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import { LoadingSpinner } from "../utils/loadingSpinner";
import { TopBar } from "../common/TopBar";
import { AgentCard } from "../components/agentHub/AgentCard";
import { CreateAgentModal } from "../components/agentHub/CreateAgentModal";
import { useConfirmationDialog } from "../components/ConfirmationDialogProvider";

// 🔁 OpenAPI-generated hooks
import { AgenticFlow, GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse, useDeleteAgentAgenticV1AgentsNameDeleteMutation, useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery } from "../slices/agentic/agenticOpenApi";

interface AgentCategory {
  name: string;
  isTag?: boolean;
}

const extractUniqueTags = (agents: AgenticFlow[]): string[] => {
  return agents
    .map((a) => a.tag || "") // keep backward compatibility
    .filter((t) => t && t.trim() !== "")
    .filter((tag, index, self) => self.indexOf(tag) === index);
};

// Map backend AgenticFlow → UI Agent (keeps both tag/tags for compatibility)
const mapFlowsToAgents = (
  flows: GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse
): AgenticFlow[] => {
  return (flows || []).map((f) => ({
    name: f.name,
    role: f.role,
    nickname: f.nickname ?? undefined,
    description: f.description,
    icon: f.icon ?? undefined,
    experts: f.experts ?? undefined,
    tag: f.tag ?? undefined,
    // keep .tags for legacy helpers/components that still read it
    tags: f.tag ?? undefined,
  })) as AgenticFlow[];
};

const ActionButton = ({
  icon,
  children,
  ...props
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
} & React.ComponentProps<typeof Button>) => {
  const theme = useTheme();
  const isDarkTheme = theme.palette.mode === "dark";
  return (
    <Button
      startIcon={icon}
      size="small"
      {...props}
      sx={{
        borderRadius: "8px",
        bgcolor: isDarkTheme ? theme.palette.action.hover : theme.palette.action.selected,
        "&:hover": {
          bgcolor: isDarkTheme ? theme.palette.action.selected : theme.palette.action.hover,
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

  // 🔁 NEW hooks
  const [triggerGetFlows, { isFetching }] = useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();
  const [deleteAgent] = useDeleteAgentAgenticV1AgentsNameDeleteMutation();
  const { showConfirmationDialog } = useConfirmationDialog();

  const handleDeleteAgent = (name: string) => {
    showConfirmationDialog({
      title: t("agentHub.confirmDeleteTitle"),
      message: t("agentHub.confirmDeleteMessage", { name }),
      onConfirm: async () => {
        try {
          await deleteAgent({ name }).unwrap(); // 🔁 signature changed
          fetchAgents();
        } catch (error) {
          console.error("Failed to delete agent:", error);
        }
      },
    });
  };

  const fetchAgents = async () => {
    try {
      const flows = await triggerGetFlows().unwrap(); // 🔁 lazy query trigger
      const mapped = mapFlowsToAgents(flows);
      setAgenticFlows(mapped);

      const tags = extractUniqueTags(mapped);
      const updatedCategories = [
        { name: "all" },
        { name: "favorites" },
        ...tags.map((tag) => ({ name: tag, isTag: true })),
      ];
      setCategories(updatedCategories);

      const savedFavorites = localStorage.getItem("favoriteAgents");
      if (savedFavorites) {
        setFavoriteAgents(JSON.parse(savedFavorites));
      }
    } catch (error) {
      console.error("Error fetching agents:", error);
    }
  };

  useEffect(() => {
    setShowElements(true);
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleTabChange = (_event: SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const filteredAgents = useMemo(() => {
    if (tabValue === 0) return agenticFlows;
    if (tabValue === 1) return agenticFlows.filter((a) => favoriteAgents.includes(a.name));
    if (categories.length > 2 && tabValue >= 2) {
      const tagName = categories[tabValue].name;
      return agenticFlows.filter((a) => (a.tag) === tagName);
    }
    return agenticFlows;
  }, [tabValue, agenticFlows, favoriteAgents, categories]);

  const toggleFavorite = (agentName: string) => {
    const updatedFavorites = favoriteAgents.includes(agentName)
      ? favoriteAgents.filter((name) => name !== agentName)
      : [...favoriteAgents, agentName];
    setFavoriteAgents(updatedFavorites);
    localStorage.setItem("favoriteAgents", JSON.stringify(updatedFavorites));
  };

  const getSectionTitle = () => {
    if (tabValue === 0) return t("agentHub.allAgents");
    if (tabValue === 1) return t("agentHub.favoriteAgents");
    if (categories.length > 2 && tabValue >= 2) return `${categories[tabValue].name} ${t("agentHub.agents")}`;
    return t("agentHub.agents");
  };

  return (
    <>
      <TopBar title={t("agentHub.title")} description={t("agentHub.description")} />
      <Container maxWidth="xl" sx={{ mb: 3 }}>
        <Fade in={showElements} timeout={1200}>
          <Paper elevation={2} sx={{ p: 2, borderRadius: 4, border: `1px solid ${theme.palette.divider}` }}>
            <Tabs
              value={tabValue}
              onChange={handleTabChange}
              variant="scrollable"
              scrollButtons="auto"
              sx={{
                "& .MuiTab-root": { textTransform: "none", fontSize: "0.9rem", fontWeight: 500, minWidth: 120 },
                "& .Mui-selected": { color: theme.palette.primary.main, fontWeight: 600 },
                "& .MuiTabs-indicator": {
                  backgroundColor: theme.palette.primary.main,
                  height: 3,
                  borderRadius: 1.5,
                },
              }}
            >
              {categories.map((category, index) => (
                <Tab
                  key={`${category.name}-${index}`}
                  label={
                    <Box sx={{ display: "flex", alignItems: "center" }}>
                      {category.isTag && <LocalOfferIcon fontSize="small" sx={{ mr: 0.5 }} />}
                      <Typography variant="body2" sx={{ textTransform: "capitalize" }}>
                        {t(`agentHub.categories.${category.name}`, category.name)}
                      </Typography>
                      {category.name === "favorites" && (
                        <Chip
                          size="small"
                          label={favoriteAgents.length}
                          sx={{
                            ml: 1,
                            height: 20,
                            fontSize: "0.7rem",
                            bgcolor: theme.palette.primary.main,
                            color: "white",
                          }}
                        />
                      )}
                      {category.isTag && (
                        <Chip
                          size="small"
                          label={agenticFlows.filter((a) => (a.tag) === category.name).length}
                          sx={{
                            ml: 1,
                            height: 20,
                            fontSize: "0.7rem",
                            bgcolor: theme.palette.primary.main,
                            color: "white",
                          }}
                        />
                      )}
                    </Box>
                  }
                />
              ))}
            </Tabs>
          </Paper>
        </Fade>
      </Container>

      <Container maxWidth="xl">
        <Fade in={showElements} timeout={1500}>
          <Paper
            elevation={2}
            sx={{ p: 3, borderRadius: 4, mb: 3, minHeight: "500px", border: `1px solid ${theme.palette.divider}` }}
          >
            {isFetching ? (
              <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
                <LoadingSpinner />
              </Box>
            ) : (
              <>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                  <Box display="flex" alignItems="center">
                    {tabValue === 1 && <StarIcon fontSize="small" sx={{ mr: 1, color: theme.palette.warning.main }} />}
                    {tabValue >= 2 && categories[tabValue]?.isTag && (
                      <LocalOfferIcon fontSize="small" sx={{ mr: 1, color: theme.palette.text.secondary }} />
                    )}
                    <Typography variant="h6" fontWeight="bold">
                      {getSectionTitle()} ({filteredAgents.length})
                    </Typography>
                  </Box>

                  <Box sx={{ display: "flex", gap: 1 }}>
                    <ActionButton icon={<SearchIcon />}>{t("agentHub.search")}</ActionButton>
                    <ActionButton icon={<FilterListIcon />}>{t("agentHub.filter")}</ActionButton>
                    <ActionButton icon={<AddIcon />} onClick={() => handleOpenCreateAgent()}>
                      {t("agentHub.create")}
                    </ActionButton>
                  </Box>
                </Box>

                {filteredAgents.length > 0 ? (
                  <Grid2 container spacing={2}>
                    {filteredAgents.map((agent) => (
                      <Grid2 key={agent.name} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
                        <Fade in timeout={1500}>
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
                    minHeight="300px"
                  >
                    <Typography variant="h6" color="textSecondary" align="center">
                      {t("agentHub.noAgents")}
                    </Typography>
                    {tabValue === 1 && (
                      <Typography variant="body2" color="textSecondary" align="center" sx={{ mt: 1 }}>
                        {t("agentHub.noFavorites")}
                      </Typography>
                    )}
                    {tabValue >= 2 && (
                      <Typography variant="body2" color="textSecondary" align="center" sx={{ mt: 1 }}>
                        {t("agentHub.noTag", { tag: categories[tabValue]?.name })}
                      </Typography>
                    )}
                  </Box>
                )}
                {isCreateModalOpen && (
                  <CreateAgentModal
                    open={isCreateModalOpen}
                    onClose={handleCloseCreateAgent}
                    onCreated={() => {
                      handleCloseCreateAgent();
                      fetchAgents(); // refresh agents
                    }}
                  />
                )}
              </>
            )}
          </Paper>
        </Fade>
      </Container>
    </>
  );
};
