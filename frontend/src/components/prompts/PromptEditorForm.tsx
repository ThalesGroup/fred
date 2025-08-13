import {
  Button,
  Stack,
  TextField,
  CircularProgress,
  Typography, // ⬅️ NEW
} from "@mui/material";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Prompt } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useState } from "react";
import { useCompletePromptAgenticV1PromptsCompletePostMutation } from "../../slices/agentic/agenticOpenApi";

const promptSchema = z.object({
  name: z.string().min(1, "Name is required"),
  content: z.string().min(1, "Prompt content is required"),
});

type PromptFormData = z.infer<typeof promptSchema>;

interface PromptEditorFormProps {
  initial?: Partial<Prompt>;
  onSave: (data: PromptFormData) => void;
  onCancel?: () => void;
  /** Optional override: if provided, we'll use this instead of the API */
  getSuggestion?: () => Promise<string>;
  loadingSuggestion?: boolean;
}

export const PromptEditorForm = ({
  initial,
  onSave,
  onCancel,
  getSuggestion,
  loadingSuggestion = false,
}: PromptEditorFormProps) => {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setValue,
    watch,
  } = useForm<PromptFormData>({
    resolver: zodResolver(promptSchema),
    defaultValues: {
      name: initial?.name || "",
      content: initial?.content || "",
    },
  });

  const [completePrompt, { isLoading: isCompleting }] =
    useCompletePromptAgenticV1PromptsCompletePostMutation();

  const [loadingHint, setLoadingHint] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null); // ⬅️ NEW

  const handleSuggest = async () => {
    setAiError(null); // clear previous error

    // If parent provided a custom suggester, use it
    if (getSuggestion) {
      setLoadingHint(true);
      try {
        const suggestion = await getSuggestion();
        if (suggestion) setValue("content", suggestion, { shouldDirty: true });
        else setAiError("No suggestion returned.");
      } catch (err) {
        console.error("Failed to fetch suggestion", err);
        setAiError("AI suggestion failed.");
      } finally {
        setLoadingHint(false);
      }
      return;
    }

    // Otherwise call our endpoint with current content (fallback to name)
    const content = (watch("content") || "").trim();
    const name = (watch("name") || "").trim();
    const basePrompt = content || name;

    if (!basePrompt) {
      setAiError("Type a name or some content first.");
      return;
    }

    try {
      const res = await completePrompt({
        promptCompleteRequest: {
          prompt: basePrompt,
          // temperature: 0.3,
          // max_tokens: 512,
          // model: undefined,
        },
      }).unwrap();

      if (res?.completion) setValue("content", res.completion, { shouldDirty: true });
      else setAiError("No completion returned.");
    } catch (err: any) {
      console.error("AI completion failed", err);
      setAiError(err?.data?.detail || "AI completion failed.");
    }
  };

  const suggestIsLoading = loadingHint || loadingSuggestion || isCompleting;

  return (
    <form onSubmit={handleSubmit(onSave)}>
      <Stack spacing={3}>
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
          minRows={14}
          {...register("content")}
          error={!!errors.content}
          helperText={errors.content?.message}
        />

        {aiError && (
          <Typography variant="caption" color="error">
            {aiError}
          </Typography>
        )}

        <Stack direction="row" spacing={2}>
          <Button type="submit" variant="contained" disabled={isSubmitting}>
            Save Prompt
          </Button>

          {onCancel && (
            <Button onClick={onCancel} variant="outlined">
              Cancel
            </Button>
          )}

          <Button
            type="button"            // ⬅️ IMPORTANT: do not submit the form
            onClick={handleSuggest}
            variant="text"
            disabled={suggestIsLoading}
            startIcon={suggestIsLoading ? <CircularProgress size={16} /> : undefined}
          >
            Get Help from AI
          </Button>
        </Stack>
      </Stack>
    </form>
  );
};
