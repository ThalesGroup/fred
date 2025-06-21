// components/profile/ChatProfiles.tsx
import { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Container,
  TextField,
  Paper,
  InputAdornment,
  Card,
  CardContent,
  Grid2,
  Stack,
  Fab,
  Button,
  Drawer,
  IconButton
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit"
import CloseIcon from "@mui/icons-material/Close"
import { useGetChatProfilesMutation, useDeleteChatProfileMutation, useUpdateChatProfileMutation, useGetChatProfileMaxTokensQuery } from "../../slices/chatProfileApi";
import { CreateChatProfileDialog } from "./ChatProfileDialog";
import { getDocumentIcon } from "../documents/DocumentIcon";
import { ChatProfile, ChatProfileEditDialog } from "./ChatProfileEditDialog";
import { useToast } from "../ToastProvider";

const getPreview = (text: string, maxChars: number = 300) => {
  if (text.length <= maxChars) return text;
  const shortened = text.slice(0, maxChars);
  const lastSpace = shortened.lastIndexOf(" ");
  return shortened.slice(0, lastSpace) + " ...";
};

const TokenBar = ({ tokens, max }: { tokens: number; max: number }) => {
  const usage = Math.min(tokens / max, 1);
  return (
    <Box
      sx={{
        height: 10,
        width: "100%",
        borderRadius: 5,
        bgcolor: "#eeeeee",
        overflow: "hidden",
        mt: 0.5,
      }}
    >
      <Box
        sx={{
          height: "100%",
          width: `${usage * 100}%`,
          bgcolor: usage < 0.7 ? "success.main" : usage < 0.9 ? "warning.main" : "error.main",
          transition: "width 0.3s ease-in-out",
        }}
      />
    </Box>
  );
};

export const ChatProfiles = () => {
  const [chatProfiles, setChatProfiles] = useState([]);
  const [search, setSearch] = useState("");
  const [getChatProfiles] = useGetChatProfilesMutation();
  const [deleteChatProfile] = useDeleteChatProfileMutation();
  const [updateChatProfile] = useUpdateChatProfileMutation();
  const [openDescription, setOpenDescription] = useState<ChatProfile | null>(null);

  const [openDialog, setOpenDialog] = useState(false);
  const [openEditDialog, setOpenEditDialog] = useState(false);
  const [currentChatProfile, setCurrentChatProfile] = useState<ChatProfile>()
  const { data } = useGetChatProfileMaxTokensQuery();
  const maxTokens = data?.max_tokens;
  const { showError } = useToast();

  useEffect(() => {
    fetchChatProfiles();
  }, []);

  const fetchChatProfiles = async () => {
    try {
      const response = await getChatProfiles().unwrap();
      setChatProfiles(response);
    } catch (e) {
      console.error("Failed to fetch chat profiles", e);
    }
  };

  // Edit chatProfile
  const handleOpenEditDialog = (chatProfile: any) => {
    setCurrentChatProfile(chatProfile);
    setOpenEditDialog(true);
  };


  const handleSaveChatProfile = async ({
    title,
    description,
    files,
  }: {
    title: string;
    description: string;
    files: File[];
  }) => {
    try {
      await updateChatProfile({
        chatProfile_id: currentChatProfile.id,
        title,
        description,
        files
      }).unwrap();

      setOpenEditDialog(false);
      setCurrentChatProfile(null);

      await fetchChatProfiles();
    } catch (error: any) {
      showError({
        summary: "Update failed",
        detail: `Could not update profile: ${error?.data?.detail || error.message}`,
      });

      await handleReloadProfile();
    }
  };


  const handleDelete = async (id: string) => {
    try {
      await deleteChatProfile({ chatProfile_id: id }).unwrap();
      setChatProfiles((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      showError({
        summary: "Delete failed",
        detail: `Could not delete profile: ${e?.data?.detail || e.message}`,
      });
    }
  };

  const filteredProfiles = chatProfiles.filter((profile) =>
    profile.title.toLowerCase().includes(search.toLowerCase())
  );

  const handleReloadProfile = async () => {
    try {
      const response = await getChatProfiles().unwrap();
      setChatProfiles(response);

      if (currentChatProfile) {
        const updated = response.find((p) => p.id === currentChatProfile.id);
        if (updated) {
          setCurrentChatProfile(updated);
        }
      }
    } catch (e) {
      showError({
        summary: "Reload failed",
        detail: `Could not reload profile: ${e?.data?.detail || e.message}`,
      });
    }
  };

  return (
    <Container maxWidth="xl" sx={{ pb: 10 }}>
      <Box mb={3}>
        <TextField
          fullWidth
          placeholder="Search profiles..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon color="action" />
                </InputAdornment>
              ),
            },
          }}
        />
      </Box>

      <Grid2 container spacing={3} alignItems="stretch">
        {filteredProfiles.map((profile) => (
          <Grid2 size={{ xs: 12 }} key={profile.id} display="flex">
            <Card
              elevation={1}
              sx={{
                borderRadius: 2,
                display: "flex",
                flexDirection: "column",
                flexGrow: 1,
                width: "100%",
                backgroundColor: "transparent",
                border: (theme) => `1px solid ${theme.palette.divider}`,
              }}
            >
              <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography variant="h6">
                    {profile.title}
                  </Typography>
                </Box>

                <Box
                  pt={2}
                  mb={1}
                  flexGrow={1}
                  display="flex"
                  justifyContent="center"
                >
                  <Box width="70%">
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        backgroundColor: (theme) => theme.palette.background.paper,
                        px: 2,
                        py: 1.5,
                        fontFamily: "monospace",
                        whiteSpace: "pre-wrap",
                        minHeight: "4.5em",
                        borderRadius: 1,
                      }}
                    >
                      {getPreview(profile.description || "No description provided.")}
                    </Typography>

                    {(profile.description?.length ?? 0) > 200 && (
                      <Button
                        size="small"
                        onClick={() => setOpenDescription(profile)}
                        sx={{ mt: 1 }}
                      >
                        View full description
                      </Button>
                    )}
                  </Box>
                </Box>


                {profile.documents?.length > 0 && (
                  <Box mt={2}>
                    <Typography variant="subtitle2" gutterBottom>
                      Documents
                    </Typography>

                    <Stack spacing={1.2} mt={1}>
                      {profile.documents?.map((doc) => (
                        <Box
                          key={doc.id}
                          display="flex"
                          alignItems="center"
                          gap={1}
                          px={1.5}
                          py={0.75}
                          borderRadius={2}
                          bgcolor="background.default"
                          border={(theme) => `1px solid ${theme.palette.divider}`}
                          boxShadow={1}
                        >
                          {getDocumentIcon(doc.document_name)}
                          <Typography variant="caption" noWrap>
                            {doc.document_name}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                )}

                <Box mt="auto" display="flex" justifyContent="space-between" alignItems="flex-end" pt={2}>
                  {/* Left side: Tokens info and gauge */}
                  <Box sx={{ width: 200}}>
                    <Typography variant="caption" color="text.secondary" whiteSpace="nowrap" sx={{ mb: 0.5 }}>
                      Tokens: {profile.tokens} / {maxTokens ?? 12000}
                    </Typography>
                    <TokenBar tokens={profile.tokens} max={maxTokens ?? 12000} />
                  </Box>

                  {/* Right side: Edit / Delete buttons */}
                  <Box display="flex" gap={1}>
                    <IconButton onClick={() => handleOpenEditDialog(profile)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton onClick={() => handleDelete(profile.id)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </Box>

              </CardContent>
            </Card>
          </Grid2>
        ))}
      </Grid2>

      {filteredProfiles.length === 0 && (
        <Paper elevation={2} sx={{ p: 4, mt: 3, borderRadius: 2, textAlign: "center" }}>
          <Typography variant="body1">No profiles found.</Typography>
        </Paper>
      )}

      <Fab
        color="primary"
        aria-label="add"
        sx={{ position: "fixed", bottom: 32, right: 32, zIndex: 10 }}
        onClick={() => setOpenDialog(true)}
      >
        <AddIcon />
      </Fab>

      <CreateChatProfileDialog
        open={openDialog}
        onClose={() => setOpenDialog(false)}
        onCreated={fetchChatProfiles}
      />

      <ChatProfileEditDialog
        open={openEditDialog}
        onClose={() => setOpenEditDialog(false)}
        onSave={handleSaveChatProfile}
        chatProfile={currentChatProfile}
        onReloadProfile={handleReloadProfile}
      />
      <Drawer
        anchor="right"
        open={Boolean(openDescription)}
        onClose={() => setOpenDescription(null)}
        PaperProps={{
          sx: { width: { xs: "100%", sm: 500 }, p: 3 },
        }}
      >
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">
            {openDescription?.title || "Profile description"}
          </Typography>
          <IconButton onClick={() => setOpenDescription(null)}>
            <CloseIcon />
          </IconButton>
        </Box>

        <Box
          sx={{
            fontFamily: "monospace",
            whiteSpace: "pre-wrap",
            lineHeight: 1.6,
            overflowY: "auto",
            color: "text.primary",
          }}
        >
          {openDescription?.description || "No description provided."}
        </Box>
      </Drawer>
    </Container>
  );
};
