// ProfileEditorModal.tsx
import {
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import * as React from "react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  buildProfileYaml,
  looksLikeYamlDoc,
} from "./resourceYamlUtils";

const profileSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  body: z.string().min(1, "Profile body is required"),
});

type ProfileFormData = z.infer<typeof profileSchema>;

type ResourceCreateLike = {
  name?: string;
  description?: string;
  labels?: string[];
  content: string; // YAML with '---'
};

interface ProfileEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: { name?: string; description?: string; labels?: string[]; content: string }) => void;
  initial?: Partial<{ name: string; description?: string; body?: string; yaml?: string; labels?: string[] }>;
  getSuggestion?: () => Promise<string>;
}

/** Modal supports two modes:
 *  - simple mode (name/description/body)
 *  - doc mode (header YAML + body) when initial content is a full YAML doc
 */
export const ProfileEditorModal: React.FC<ProfileEditorModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initial,
  getSuggestion,
}) => {

  // ----- Simple mode form (create) -----
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
    defaultValues: { name: "", description: "", body: "" },
  });

  // ----- Doc mode state (kept but UI is simple-only now) -----
  const [suggesting, setSuggesting] = useState(false);

  const handleAIHelp = async () => {
    if (!getSuggestion) return;
    try {
      setSuggesting(true);
      const suggestion = await getSuggestion();
      if (!suggestion) return;
      setValue("body", suggestion);
    } catch (err) {
      console.error("AI profile suggestion failed", err);
    } finally {
      setSuggesting(false);
    }
  };

  // ----- Submit handlers -----
  const onSubmitSimple = (data: ProfileFormData) => {
    const body = (data.body || "").trim();
    const content = looksLikeYamlDoc(body)
      ? body
      : buildProfileYaml({
        name: data.name,
        description: data.description || undefined,
        labels: undefined,
        body,
      });

    const payload: ResourceCreateLike = {
      name: data.name,
      description: data.description || undefined,
      content,
    };
    onSave(payload);
    onClose();
  };

  return (
    <Dialog open={isOpen} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{initial ? "Edit Profile" : "Create Profile"}</DialogTitle>

      {/* Simple form only */}
      <form onSubmit={handleSubmit(onSubmitSimple)}>
        <DialogContent>
          <Stack spacing={3} mt={1}>
            <TextField
              label="Profile Name"
              fullWidth
              {...register("name")}
              error={!!errors.name}
              helperText={errors.name?.message}
            />
            <TextField
              label="Description (optional)"
              fullWidth
              {...register("description")}
              error={!!errors.description}
              helperText={errors.description?.message}
            />
            <TextField
              label="Profile Body"
              fullWidth
              multiline
              minRows={14}
              {...register("body")}
              error={!!errors.body}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} variant="outlined">Cancel</Button>
          <Button
            onClick={handleAIHelp}
            variant="text"
            disabled={!getSuggestion || suggesting}
            startIcon={suggesting ? <CircularProgress size={16} /> : undefined}
          >
            Get Help from AI
          </Button>
          <Button type="submit" variant="contained" disabled={isSubmitting}>
            Save
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};
