// Copyright Thales 2025

import {
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { buildTemplateYaml } from "./resourceYamlUtils";

/** ---- Minimal form schema ---- */
const templateSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  format: z.enum(["markdown", "html", "text", "json"]), // required
  body: z.string().min(1, "Template body is required"),
});
type TemplateFormData = z.infer<typeof templateSchema>;


type ResourceCreateLike = {
  name?: string;
  description?: string;
  labels?: string[];
  content: string; // final YAML with '---' separator
};

interface TemplateEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: ResourceCreateLike) => void; // parent will call createResource(payload, tagId)
  /** Optional initial values when editing later */
  initial?: Partial<TemplateFormData & { labels?: string[] }>;
  /** Optional async suggester for the body text */
  getSuggestion?: () => Promise<string>;
}

/** ---- Component ---- */

export const TemplateEditorModal = ({
  isOpen,
  onClose,
  onSave,
  initial,
  getSuggestion,
}: TemplateEditorModalProps) => {
  const {
    register,
    handleSubmit,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TemplateFormData>({
    
    resolver: zodResolver(templateSchema),
    defaultValues: {
      name: "",
      description: "",
      format: "markdown",
      body: "",
    },
  });

  useEffect(() => {
    reset({
      name: initial?.name ?? "",
      description: initial?.description ?? "",
      format: (initial?.format as any) ?? "markdown",
      body: (initial as any)?.body ?? "",
    });
  }, [initial, reset, isOpen]);

  const handleAIHelp = async () => {
    if (!getSuggestion) return;
    try {
      const suggestion = await getSuggestion();
      if (suggestion) setValue("body", suggestion);
    } catch (err) {
      console.error("AI template suggestion failed", err);
    }
  };

  const onSubmit = (data: TemplateFormData) => {
    const body = (data.body || "").trim();

    // If the user pasted full YAML already, pass through; else build header+schema
    const looksLikeYaml = body.includes("\n---\n") && /^[A-Za-z0-9_-]+:\s/m.test(body);
    const content = looksLikeYaml
      ? body
      : buildTemplateYaml({
          name: data.name,
          description: data.description || undefined,
          labels: undefined,
          format: data.format,
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
      <DialogTitle>{initial ? "Edit Template" : "Create Template"}</DialogTitle>
      <form onSubmit={handleSubmit(onSubmit)}>
        <DialogContent>
          <Stack spacing={3} mt={1}>
            <TextField
              label="Template Name"
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
              label="Format"
              select
              fullWidth
              {...register("format")}
              error={!!errors.format}
              helperText={errors.format?.message}
            >
              <MenuItem value="markdown">Markdown</MenuItem>
              <MenuItem value="html">HTML</MenuItem>
              <MenuItem value="docx">DOCX</MenuItem>
              <MenuItem value="json">JSON</MenuItem>
            </TextField>
            <TextField
              label="Template Body"
              fullWidth
              multiline
              minRows={14}
              {...register("body")}
              error={!!errors.body}
              helperText={errors.body?.message || "Use {placeholders} to define inputs."}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} variant="outlined">Cancel</Button>
          <Button onClick={handleAIHelp} variant="text" disabled={!getSuggestion}>
            {false ? <CircularProgress size={16} /> : null}
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
