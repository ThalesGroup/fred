// PromptEditorModal.tsx
// Aligned with Template editor: collects name, (optional) description, and body.
// Builds prompt YAML on submit using shared helpers.

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
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { buildPromptYaml, looksLikeYamlDoc } from "./resourceYamlUtils";

const promptSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  body: z.string().min(1, "Prompt body is required"),
});

type PromptFormData = z.infer<typeof promptSchema>;

type ResourceCreateLike = {
  name?: string;
  description?: string;
  labels?: string[];
  content: string; // YAML with '---'
};

interface PromptEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: { name?: string; description?: string; labels?: string[]; content: string }) => void;
  initial?: Partial<{ name: string; description?: string; body?: string; labels?: string[] }>;
  getSuggestion?: () => Promise<string>;
}

export const PromptEditorModal: React.FC<PromptEditorModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initial,
  getSuggestion,
}) => {
  const [suggesting, setSuggesting] = useState(false);

  const {
    register,
    handleSubmit,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PromptFormData>({
    resolver: zodResolver(promptSchema),
    defaultValues: {
      name: "",
      description: "",
      body: "",
    },
  });

  useEffect(() => {
    if (!isOpen) return;
    reset({
      name: initial?.name ?? "",
      description: initial?.description ?? "",
      body: (initial as any)?.yaml ?? (initial as any)?.body ?? "",
    });
  }, [initial, reset, isOpen]);

  const handleAIHelp = async () => {
    if (!getSuggestion) return;
    try {
      setSuggesting(true);
      const suggestion = await getSuggestion();
      if (suggestion) setValue("body", suggestion);
    } catch (err) {
      console.error("AI prompt suggestion failed", err);
    } finally {
      setSuggesting(false);
    }
  };

  const onSubmit = (data: PromptFormData) => {
    const body = (data.body || "").trim();
    const content = looksLikeYamlDoc(body)
      ? body
      : buildPromptYaml({
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
      <DialogTitle>{initial ? "Edit Prompt" : "Create Prompt"}</DialogTitle>
      <form onSubmit={handleSubmit(onSubmit)}>
        <DialogContent>
          <Stack spacing={3} mt={1}>
            <TextField
              label="Prompt Name"
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
              label="Prompt Body"
              fullWidth
              multiline
              minRows={14}
              {...register("body")}
              error={!!errors.body}
              helperText={errors.body?.message || "Tip: use {placeholders} to define inputs."}
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
