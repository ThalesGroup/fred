import { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Container,
  TextField,
  InputAdornment,
  Grid2,
  Fab,
  Paper,
  IconButton,
  Drawer
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";

import { useToast } from "../ToastProvider";
import { KnowledgeContextItem } from "../knowledgeContext/KnowledgeContextItem";
import { KnowledgeContextCreateDialog } from "../knowledgeContext/KnowledgeContextCreateDialog";
import { KnowledgeContextEditDialog } from "../knowledgeContext/KnowledgeContextEditDialog";
import {
  useDeleteKnowledgeContextMutation,
  useLazyGetKnowledgeContextsQuery,
  useUpdateKnowledgeContextMutation
} from "../../slices/knowledgeContextApi";
import { useTranslation } from "react-i18next";

export const ChatProfiles = () => {
  const { t } = useTranslation();
  const [chatProfiles, setChatProfiles] = useState([]);
  const [search, setSearch] = useState("");
  const [getChatProfiles] = useLazyGetKnowledgeContextsQuery();
  const [deleteChatProfile] = useDeleteKnowledgeContextMutation();
  const [updateChatProfile] = useUpdateKnowledgeContextMutation();
  const [openDescription, setOpenDescription] = useState(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [openEditDialog, setOpenEditDialog] = useState(false);
  const [currentChatProfile, setCurrentChatProfile] = useState(null);
  const { showError } = useToast();

  useEffect(() => {
    fetchChatProfiles();
  }, []);

  const fetchChatProfiles = async () => {
    try {
      const response = await getChatProfiles({ tag: "chat_profile" }).unwrap();
      setChatProfiles(response);
    } catch (e) {
      console.error("Failed to fetch chat profiles", e);
    }
  };

  const handleOpenEditDialog = (profile) => {
    setCurrentChatProfile(profile);
    setOpenEditDialog(true);
  };

  const handleSaveChatProfile = async ({ title, description, files }) => {
    try {
      await updateChatProfile({
        knowledgeContext_id: currentChatProfile.id,
        title,
        description,
        files,
      }).unwrap();
      setOpenEditDialog(false);
      setCurrentChatProfile(null);
      await fetchChatProfiles();
    } catch (error) {
      showError({
        summary: t("profile.chat.updateError"),
        detail: `${error?.data?.detail || error.message}`,
      });
      await handleReloadProfile();
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteChatProfile({ knowledgeContext_id: id }).unwrap();
      setChatProfiles((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      showError({
        summary: t("profile.chat.deleteError"),
        detail: `${e?.data?.detail || e.message}`,
      });
    }
  };

  const handleReloadProfile = async () => {
    try {
      const response = await getChatProfiles({ tag: "chat_profile" }).unwrap();
      setChatProfiles(response);
      if (currentChatProfile) {
        const updated = response.find((p) => p.id === currentChatProfile.id);
        if (updated) setCurrentChatProfile(updated);
      }
    } catch (e) {
      showError({
        summary: t("profile.chat.reloadError"),
        detail: `${e?.data?.detail || e.message}`,
      });
    }
  };

  const filteredProfiles = chatProfiles.filter((p) =>
    p.title.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Container maxWidth="xl" sx={{ pb: 10 }}>
      <Box mb={3}>
        <TextField
          fullWidth
          placeholder={t("profile.chat.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon color="action" />
              </InputAdornment>
            ),
          }}
        />
      </Box>

      <Grid2 container spacing={3} alignItems="stretch">
        {filteredProfiles.map((profile) => (
          <Grid2 size={{ xs: 6 }} key={profile.id} display="flex">
            <KnowledgeContextItem
              id={profile.id}
              title={profile.title}
              description={profile.description}
              documents={profile.documents}
              onEdit={handleOpenEditDialog}
              onDelete={handleDelete}
              onViewDescription={setOpenDescription}
              allowDocumentDescription={false}
              allowDocuments={true}
            />
          </Grid2>
        ))}
      </Grid2>

      {filteredProfiles.length === 0 && (
        <Paper elevation={2} sx={{ p: 4, mt: 3, borderRadius: 2, textAlign: "center" }}>
          <Typography variant="body1">{t("profile.chat.noProfiles")}</Typography>
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

      <KnowledgeContextCreateDialog
        open={openDialog}
        onClose={() => setOpenDialog(false)}
        onCreated={fetchChatProfiles}
        allowDocumentDescription={false}
        dialogTitle={t("profile.chat.dialogTitle")}
        tag="chat_profile"
      />

      <KnowledgeContextEditDialog
        open={openEditDialog}
        onClose={() => setOpenEditDialog(false)}
        onSave={handleSaveChatProfile}
        onReloadContext={handleReloadProfile}
        context={currentChatProfile}
        allowDocumentDescription={false}
        dialogTitle={t("profile.chat.dialogTitle")}
      />

      <Drawer
        anchor="right"
        open={Boolean(openDescription)}
        onClose={() => setOpenDescription(null)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 500 }, p: 3 } }}
      >
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">
            {openDescription?.title || t("profile.chat.drawerTitle")}
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
          {openDescription?.description || t("profile.chat.noDescription")}
        </Box>
      </Drawer>
    </Container>
  );
};
