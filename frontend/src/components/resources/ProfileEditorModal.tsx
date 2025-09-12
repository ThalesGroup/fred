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
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import yaml from "js-yaml";
import {
  buildProfileYaml,
  looksLikeYamlDoc,
  splitFrontMatter,
  buildFrontMatter,
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
  const incomingDoc = useMemo(() => (initial as any)?.yaml ?? (initial as any)?.body ?? "", [initial]);
  const isDocMode = useMemo(() => looksLikeYamlDoc(incomingDoc), [incomingDoc]);

  // ----- Simple mode form (create) -----
  const {
    register,
    handleSubmit,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
    defaultValues: { name: "", description: "", body: "" },
  });

  // ----- Doc mode state (edit header+body) -----
  const [headerText, setHeaderText] = useState<string>("");
  const [bodyText, setBodyText] = useState<string>("");
  const [headerError, setHeaderError] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    if (isDocMode) {
      const { header, body } = splitFrontMatter(incomingDoc);
      setHeaderText(yaml.dump(header).trim());
      setBodyText(body);
    } else {
      reset({
        name: initial?.name ?? "",
        description: initial?.description ?? "",
        body: incomingDoc || "",
      });
    }
  }, [isOpen, isDocMode, incomingDoc, initial?.name, initial?.description, reset]);

  const handleAIHelp = async () => {
    if (!getSuggestion) return;
    try {
      setSuggesting(true);
      const suggestion = await getSuggestion();
      if (!suggestion) return;
      if (isDocMode) {
        setBodyText(suggestion);
      } else {
        setValue("body", suggestion);
      }
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

  const onSubmitDoc = () => {
    // Parse header YAML back to object
    let headerObj: Record<string, any>;
    try {
      headerObj = (yaml.load(headerText || "") as Record<string, any>) ?? {};
      setHeaderError(null);
    } catch (e: any) {
      setHeaderError(e?.message || "Invalid YAML");
      return;
    }
    // Ensure kind (UI safety; backend can still validate)
    if (!headerObj.kind) headerObj.kind = "profile";

    const content = buildFrontMatter(headerObj, bodyText);
    onSave({
      content,
      name: headerObj.name,
      description: headerObj.description,
      labels: headerObj.labels,
    });
    onClose();
  };

  return (
    <Dialog open={isOpen} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{initial ? "Edit Profile" : "Create Profile"}</DialogTitle>

      {/* Render either simple or doc form */}
      {isDocMode ? (
        <>
          <DialogContent>
            <Stack spacing={3} mt={1}>
              <TextField
                label="Header (YAML)"
                fullWidth
                multiline
                minRows={10}
                value={headerText}
                onChange={(e) => setHeaderText(e.target.value)}
                error={!!headerError}
                helperText={headerError || "Edit profile metadata (version, name, labels, schema, etc.)"}
              />
              <TextField
                label="Body"
                fullWidth
                multiline
                minRows={14}
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                helperText="Tip: use {placeholders} to define inputs."
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
            <Button onClick={onSubmitDoc} variant="contained">Save</Button>
          </DialogActions>
        </>
      ) : (
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
      )}
    </Dialog>
  );
};
