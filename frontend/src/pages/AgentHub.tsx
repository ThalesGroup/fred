import { PageBodyWrapper } from "../common/PageBodyWrapper";
import {
  Box,
  Typography,
  useTheme,
  Container,
  Paper,
  Card,
  CardContent,
  Button,
  Avatar,
  Chip,
  Fade,
  Tabs,
  Tab,
  Tooltip,
  IconButton} from "@mui/material";
import { useState, useEffect, SyntheticEvent } from "react";
import SearchIcon from "@mui/icons-material/Search";
import FilterListIcon from "@mui/icons-material/FilterList";
import StarIcon from '@mui/icons-material/Star';
import StarOutlineIcon from '@mui/icons-material/StarOutline';
import DescriptionIcon from '@mui/icons-material/Description';
import { LoadingSpinner } from "../utils/loadingSpinner";
import { getAgentBadge } from "../utils/avatar";
import Grid2 from "@mui/material/Grid2";
import { KeyCloakService } from "../security/KeycloakService";
import ContextManagementModal from "../components/ContextManagementModal";
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import { useGetChatBotAgenticFlowsMutation } from "../slices/chatApi";

interface AgentCategory {
  name: string;
  isTag?: boolean;
}

export const AgentHub = () => {
  const theme = useTheme();
  const isDarkTheme = theme.palette.mode === "dark";

  // États
  const [agenticFlows, setAgenticFlows] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [tabValue, setTabValue] = useState(0);
  const [showElements, setShowElements] = useState(false);
  const [favoriteAgents, setFavoriteAgents] = useState<string[]>([]);
  const [categories, setCategories] = useState<AgentCategory[]>([
    { name: "all" },
    { name: "favorites" },
  ]);

  // États pour la gestion du contexte
  const [contextModalOpen, setContextModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [, setUserInfo] = useState({
    name: KeyCloakService.GetUserName(),
    isAdmin: KeyCloakService.GetUserRoles().includes("admin"),
    roles: KeyCloakService.GetUserRoles()
  });

  // API Hooks
  const [getAgenticFlows] = useGetChatBotAgenticFlowsMutation();

  useEffect(() => {
    setShowElements(true);
    setUserInfo({
      name: KeyCloakService.GetUserName(),
      isAdmin: KeyCloakService.GetUserRoles().includes("admin"),
      roles: KeyCloakService.GetUserRoles()
    });

    // Récupérer les agents
    const fetchAgents = async () => {
      try {
        setIsLoading(true);
        const response = await getAgenticFlows().unwrap();
        console.log("Agents récupérés:", response);
        setAgenticFlows(response);

        // Extraire les tags uniques des agents (ignorer les tags vides ou null)
        const tags = response
          .map(agent => agent.tags)
          .filter(tag => tag && tag.trim() !== "")
          .filter((tag, index, self) => self.indexOf(tag) === index);
        
        console.log("Tags uniques trouvés:", tags);

        // Mettre à jour les catégories avec les tags
        const updatedCategories = [
          { name: "all" },
          { name: "favorites" },
          ...tags.map(tag => ({ name: tag, isTag: true }))
        ];
        setCategories(updatedCategories);

        // Récupérer les favoris du localStorage
        const savedFavorites = localStorage.getItem('favoriteAgents');
        if (savedFavorites) {
          setFavoriteAgents(JSON.parse(savedFavorites));
        }
      } catch (error) {
        console.error('Error fetching agents:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchAgents();
  }, [getAgenticFlows]);

  // Gestionnaire de changement d'onglet
  const handleTabChange = (_event: SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // Fonction pour filtrer les agents selon l'onglet actif
  const getFilteredAgents = () => {
    if (tabValue === 0) return agenticFlows; // All
    if (tabValue === 1) return agenticFlows.filter(agent => favoriteAgents.includes(agent.name)); // Favorites
    
    // Si on a plus de 2 catégories (all + favorites + tags), on filtre par tag
    if (categories.length > 2 && tabValue >= 2) {
      const tagName = categories[tabValue].name;
      return agenticFlows.filter(agent => agent.tag === tagName);
    }
    
    return agenticFlows;
  };

  // Gérer les agents favoris
  const toggleFavorite = (agentName: string) => {
    let updatedFavorites;
    if (favoriteAgents.includes(agentName)) {
      updatedFavorites = favoriteAgents.filter(name => name !== agentName);
    } else {
      updatedFavorites = [...favoriteAgents, agentName];
    }
    setFavoriteAgents(updatedFavorites);
    localStorage.setItem('favoriteAgents', JSON.stringify(updatedFavorites));
  };
  
  // Gérer l'ouverture de la modale de contexte
  const openContextModal = (agent) => {
    setSelectedAgent(agent);
    setContextModalOpen(true);
  };

  // Obtenir le titre de la section actuelle
  const getSectionTitle = () => {
    if (tabValue === 0) return "All Agents";
    if (tabValue === 1) return "Favorite Agents";
    if (categories.length > 2 && tabValue >= 2) {
      return `${categories[tabValue].name} Agents`;
    }
    return "Agents";
  };

  return (
    <PageBodyWrapper>
      {/* Hero Section */}
      <Box
        sx={{
          position: "relative",
          backgroundSize: "cover",
          backgroundPosition: "center",
          py: { xs: 3, md: 4 },
          mb: 3,
          borderRadius: 2,
          boxShadow: theme.shadows[4]
        }}
      >
        <Container maxWidth="xl">
          <Fade in={showElements} timeout={1000}>
            <Grid2 container alignItems="center" spacing={2}>
              <Grid2 size={{xs:12, md:8}}>
                <Box>
                  <Typography variant="h4" fontWeight="bold" gutterBottom>
                    Agent Hub
                  </Typography>
                  <Typography
                    variant="body2"
                    color="textSecondary"
                    sx={{ maxWidth: "700px" }}
                  >
                    Explore and manage all available AI agents to enhance your workflow
                  </Typography>
                </Box>
              </Grid2>
            </Grid2>
          </Fade>
        </Container>
      </Box>

      {/* Tabs Section */}
      <Container maxWidth="xl" sx={{ mb: 3 }}>
        <Fade in={showElements} timeout={1200}>
          <Paper
            elevation={2}
            sx={{
              p: 2,
              borderRadius: 4,
              border: `1px solid ${theme.palette.divider}`
            }}
          >
            <Tabs
              value={tabValue}
              onChange={handleTabChange}
              variant="scrollable"
              scrollButtons="auto"
              sx={{
                '& .MuiTab-root': {
                  textTransform: 'none',
                  fontSize: '0.9rem',
                  fontWeight: 500,
                  minWidth: 120,
                },
                '& .Mui-selected': {
                  color: theme.palette.primary.main,
                  fontWeight: 600,
                },
                '& .MuiTabs-indicator': {
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
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {category.isTag && (
                        <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, fontSize: '0.9rem' }} />
                      )}
                      <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                        {category.name}
                      </Typography>
                      {category.name === "favorites" && (
                        <Chip
                          size="small"
                          label={favoriteAgents.length}
                          sx={{
                            ml: 1, 
                            height: 20, 
                            fontSize: '0.7rem',
                            bgcolor: theme.palette.primary.main,
                            color: 'white'
                          }}
                        />
                      )}
                      {category.isTag && (
                        <Chip
                          size="small"
                          label={agenticFlows.filter(agent => agent.tag === category.name).length}
                          sx={{
                            ml: 1, 
                            height: 20, 
                            fontSize: '0.7rem',
                            bgcolor: theme.palette.primary.main,
                            color: 'white'
                          }}
                        />
                      )}
                    </Box>
                  }
                  id={`agent-tab-${index}`}
                  aria-controls={`agent-tabpanel-${index}`}
                />
              ))}
            </Tabs>
          </Paper>
        </Fade>
      </Container>

      {/* Agents Grid */}
      <Container maxWidth="xl">
        <Fade in={showElements} timeout={1500}>
          <Paper
            elevation={2}
            sx={{
              p: 3,
              borderRadius: 4,
              mb: 3,
              minHeight: '500px',
              border: `1px solid ${theme.palette.divider}`,
              position: 'relative'
            }}
          >
            {isLoading ? (
              <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
                <LoadingSpinner />
              </Box>
            ) : (
              <>
                <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    {tabValue === 1 && (
                      <StarIcon fontSize="small" sx={{ mr: 1, color: theme.palette.warning.main }} />
                    )}
                    {tabValue >= 2 && categories[tabValue]?.isTag && (
                      <LocalOfferIcon fontSize="small" sx={{ mr: 1, color: theme.palette.text.secondary }} />
                    )}
                    <Typography variant="h6" fontWeight="bold">
                      {getSectionTitle()} ({getFilteredAgents().length})
                    </Typography>
                  </Box>
                  
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <Button 
                      startIcon={<SearchIcon />} 
                      size="small"
                      sx={{ 
                        borderRadius: '8px',
                        bgcolor: isDarkTheme ? theme.palette.action.hover : theme.palette.action.selected,
                        '&:hover': {
                          bgcolor: isDarkTheme ? theme.palette.action.selected : theme.palette.action.hover,
                        }
                      }}
                    >
                      Search
                    </Button>
                    <Button 
                      startIcon={<FilterListIcon />} 
                      size="small"
                      sx={{ 
                        borderRadius: '8px',
                        bgcolor: isDarkTheme ? theme.palette.action.hover : theme.palette.action.selected,
                        '&:hover': {
                          bgcolor: isDarkTheme ? theme.palette.action.selected : theme.palette.action.hover,
                        }
                      }}
                    >
                      Filter
                    </Button>
                  </Box>
                </Box>

                {/* Affichage des agents - Format original pour All, mais avec tags visibles */}
                <Grid2 container spacing={2}>
                  {getFilteredAgents().map((agent) => (
                    <Grid2 size={{xs:12, sm:6, md:4, lg:3}} key={agent.name}>
                      <Fade in={true} timeout={1500}>
                        <Card
                          sx={{
                            height: '100%',
                            display: 'flex',
                            flexDirection: 'column',
                            borderRadius: 3,
                            boxShadow: theme.shadows[2],
                            transition: 'transform 0.2s, box-shadow 0.2s',
                            '&:hover': {
                              transform: 'translateY(-4px)',
                              boxShadow: theme.shadows[4],
                            },
                            border: `1px solid ${theme.palette.divider}`,
                          }}
                        >
                          <Box
                            sx={{
                              p: 2,
                              pb: 0,
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'flex-start'
                            }}
                          >
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Box sx={{ mr: 1.5 }}>
                                {getAgentBadge(agent.nickname)}
                              </Box>
                              <Box>
                                <Typography variant="h6" component="div" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                                  {agent.nickname}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  {agent.role}
                                </Typography>
                              </Box>
                            </Box>

                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              {agent.tag && agent.tag.trim() !== "" && (
                                <Tooltip title={`Tagged: ${agent.tag}`}>
                                  <Chip
                                    icon={<LocalOfferIcon fontSize="small" />}
                                    label={agent.tag}
                                    size="small"
                                    sx={{ 
                                      mr: 1,
                                      height: 24, 
                                      fontSize: '0.7rem',
                                    }}
                                  />
                                </Tooltip>
                              )}

                              <IconButton
                                size="small"
                                onClick={() => toggleFavorite(agent.name)}
                                sx={{ 
                                  color: favoriteAgents.includes(agent.name) ? 'warning.main' : 'text.secondary',
                                }}
                              >
                                {favoriteAgents.includes(agent.name) ? <StarIcon /> : <StarOutlineIcon />}
                              </IconButton>
                            </Box>
                          </Box>

                          <CardContent sx={{ flexGrow: 1, pt: 1 }}>
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{
                                display: '-webkit-box',
                                WebkitLineClamp: 3,
                                WebkitBoxOrient: 'vertical',
                                overflow: 'hidden',
                                mb: 2,
                                minHeight: '3.6em',
                                fontSize: '0.85rem'
                              }}
                            >
                              {agent.description}
                            </Typography>
                            
                            <Box sx={{ mt: 2, display: 'flex', alignItems: 'center' }}>
                              <Button
                                size="small"
                                startIcon={<DescriptionIcon />}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openContextModal(agent);
                                }}
                                sx={{ 
                                  ml: 1,
                                  textTransform: 'none',
                                  fontSize: '0.75rem',
                                  fontWeight: 'normal',
                                  color: theme.palette.primary.main,
                                }}
                              >
                                Manage Context
                              </Button>
                            </Box>

                            {agent.experts && agent.experts.length > 0 && (
                              <Box sx={{ mt: 2 }}>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                                  Expert integrations:
                                </Typography>
                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                  {agent.experts.map(expertName => {
                                    const expert = agenticFlows.find(a => a.name === expertName);
                                    return expert ? (
                                      <Tooltip key={expertName} title={expert.description}>
                                        <Chip
                                          avatar={<Avatar sx={{ width: 20, height: 20 }}>{getAgentBadge(expert.nickname)}</Avatar>}
                                          label={expert.nickname}
                                          size="small"
                                          sx={{ 
                                            height: 24, 
                                            fontSize: '0.7rem',
                                            '& .MuiChip-avatar': {
                                              width: 18,
                                              height: 18,
                                            }
                                          }}
                                        />
                                      </Tooltip>
                                    ) : null;
                                  })}
                                </Box>
                              </Box>
                            )}
                          </CardContent>
                        </Card>
                      </Fade>
                    </Grid2>
                  ))}
                </Grid2>

                {getFilteredAgents().length === 0 && (
                  <Box
                    display="flex"
                    flexDirection="column"
                    alignItems="center"
                    justifyContent="center"
                    minHeight="300px"
                  >
                    <Typography variant="h6" color="textSecondary" align="center">
                      No agents found
                    </Typography>
                    {tabValue === 1 && (
                      <Typography variant="body2" color="textSecondary" align="center" sx={{ mt: 1 }}>
                        You haven't added any agents to your favorites yet
                      </Typography>
                    )}
                    {tabValue >= 2 && (
                      <Typography variant="body2" color="textSecondary" align="center" sx={{ mt: 1 }}>
                        No agents with tag "{categories[tabValue]?.name}"
                      </Typography>
                    )}
                  </Box>
                )}
              </>
            )}
          </Paper>
        </Fade>
      </Container>

      {/* Context Management Modal */}
      <ContextManagementModal
        open={contextModalOpen}
        onClose={() => setContextModalOpen(false)}
        agent={selectedAgent}
        getAgentBadge={getAgentBadge}
      />
    </PageBodyWrapper>
  );
};