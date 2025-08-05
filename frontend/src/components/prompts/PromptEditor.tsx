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
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Prompt } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

const promptSchema = z.object({
  name: z.string().min(1, "Name is required"),
  content: z.string().min(1, "Prompt content is required"),
});

type PromptFormData = z.infer<typeof promptSchema>;

interface EditPromptModalProps {
  prompt: Prompt | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (updated: Prompt) => void;
  getSuggestion?: () => Promise<string>; // optional AI helper
}

export const EditPromptModal = ({
  prompt,
  isOpen,
  onClose,
  onSave,
  getSuggestion,
}: EditPromptModalProps) => {
  const [loadingSuggestion, setLoadingSuggestion] = useState(false);

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
      content: "",
    },
  });

  useEffect(() => {
    if (prompt) {
      reset({
        name: prompt.name,
        content: prompt.content,
      });
    } else {
      reset({
        name: "",
        content: "",
      });
    }
  }, [prompt, reset]);

  const handleAIHelp = async () => {
    if (!getSuggestion) return;
    setLoadingSuggestion(true);
    try {
      const suggestion = await getSuggestion();
      setValue("content", suggestion);
    } catch (err) {
      console.error("AI suggestion failed", err);
    } finally {
      setLoadingSuggestion(false);
    }
  };

  const onSubmit = (data: PromptFormData) => {
    const updatedPrompt: Prompt = {
      ...prompt,
      ...data,
      id: prompt?.id ?? crypto.randomUUID(), // TEMP ID for creation
      tags: prompt?.tags ?? [],
      owner_id: prompt?.owner_id ?? "",
      created_at: prompt?.created_at ?? new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    onSave(updatedPrompt);
    onClose();
  };

  return (
    <Dialog open={isOpen} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{prompt ? "Edit Prompt" : "Create Prompt"}</DialogTitle>
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
              label="Prompt Content"
              fullWidth
              multiline
              minRows={6}
              {...register("content")}
              error={!!errors.content}
              helperText={errors.content?.message}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} variant="outlined">Cancel</Button>
          {getSuggestion && (
            <Button
              onClick={handleAIHelp}
              variant="text"
              disabled={loadingSuggestion}
              startIcon={loadingSuggestion ? <CircularProgress size={16} /> : undefined}
            >
              Get Help from AI
            </Button>
          )}
          <Button type="submit" variant="contained" disabled={isSubmitting}>
            Save
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
};
