import {
  Button,
  Stack,
  TextField,
  CircularProgress,
} from "@mui/material";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Prompt } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useState } from "react";

const promptSchema = z.object({
  name: z.string().min(1, "Name is required"),
  content: z.string().min(1, "Prompt content is required"),
});

type PromptFormData = z.infer<typeof promptSchema>;

interface PromptEditorFormProps {
  initial?: Partial<Prompt>;
  onSave: (data: PromptFormData) => void;
  onCancel?: () => void;
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
  } = useForm<PromptFormData>({
    resolver: zodResolver(promptSchema),
    defaultValues: {
      name: initial?.name || "",
      content: initial?.content || "",
    },
  });

  const [loadingHint, setLoadingHint] = useState(false);

  const handleSuggest = async () => {
    if (!getSuggestion) return;
    setLoadingHint(true);
    try {
      const suggestion = await getSuggestion();
      setValue("content", suggestion);
    } catch (err) {
      console.error("Failed to fetch suggestion", err);
    } finally {
      setLoadingHint(false);
    }
  };

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
          minRows={6}
          {...register("content")}
          error={!!errors.content}
          helperText={errors.content?.message}
        />
        <Stack direction="row" spacing={2}>
          <Button
            type="submit"
            variant="contained"
            disabled={isSubmitting}
          >
            Save Prompt
          </Button>
          {onCancel && (
            <Button onClick={onCancel} variant="outlined">
              Cancel
            </Button>
          )}
          {getSuggestion && (
            <Button
              onClick={handleSuggest}
              variant="text"
              disabled={loadingHint || loadingSuggestion}
              startIcon={
                loadingHint || loadingSuggestion ? (
                  <CircularProgress size={16} />
                ) : undefined
              }
            >
              Get Help from AI
            </Button>
          )}
        </Stack>
      </Stack>
    </form>
  );
};
