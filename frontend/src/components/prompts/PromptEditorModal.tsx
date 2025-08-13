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
import { useCompletePromptAgenticV1PromptsCompletePostMutation } from "../../slices/agentic/agenticOpenApi";

const promptSchema = z.object({
  name: z.string().min(1, "Name is required"),
  content: z.string().min(1, "Prompt content is required"),
});

type PromptFormData = z.infer<typeof promptSchema>;

interface PromptEditorModalProps {
  prompt: Prompt | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (updated: Prompt) => void;
  /** Optional override: if provided, we'll use this instead of the API */
  getSuggestion?: () => Promise<string>;
}

export const PromptEditorModal = ({
  prompt,
  isOpen,
  onClose,
  onSave,
  getSuggestion,
}: PromptEditorModalProps) => {
  const [loadingSuggestion, setLoadingSuggestion] = useState(false);

  const {
    register,
    handleSubmit,
    setValue,
    reset,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<PromptFormData>({
    resolver: zodResolver(promptSchema),
    defaultValues: {
      name: "",
      content: "",
    },
  });

  // RTK Query mutation for /agentic/v1/prompts/complete
  const [completePrompt, { isLoading: isCompleting }] =
    useCompletePromptAgenticV1PromptsCompletePostMutation();

  useEffect(() => {
    if (prompt) {
      reset({
        name: prompt.name,
        content: prompt.content,
      });
    } else {
      reset({ name: "", content: "" });
    }
  }, [prompt, reset]);

  const handleAIHelp = async () => {
    // If a custom suggester is provided, prefer it
    if (getSuggestion) {
      setLoadingSuggestion(true);
      try {
        const suggestion = await getSuggestion();
        if (suggestion) setValue("content", suggestion);
      } catch (err) {
        console.error("AI suggestion failed", err);
      } finally {
        setLoadingSuggestion(false);
      }
      return;
    }

    // Otherwise call our backend
    const content = (getValues("content") || "").trim();
    const name = (getValues("name") || "").trim();
    const basePrompt = content || name;
    if (!basePrompt) return;

    try {
      const res = await completePrompt({
        promptCompleteRequest: {
          prompt: basePrompt,
          // temperature: 0.3,
          // max_tokens: 512,
          // model: undefined,
        },
      }).unwrap();

      if (res?.completion) setValue("content", res.completion);
    } catch (err) {
      console.error("AI completion failed", err);
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
              minRows={14}  // roomier editor here too
              {...register("content")}
              error={!!errors.content}
              helperText={errors.content?.message}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} variant="outlined">Cancel</Button>
          <Button
            onClick={handleAIHelp}
            variant="text"
            disabled={loadingSuggestion || isCompleting}
            startIcon={(loadingSuggestion || isCompleting) ? <CircularProgress size={16} /> : undefined}
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
