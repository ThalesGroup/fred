import {
    Dialog, DialogTitle, DialogContent, DialogActions,
    TextField, Button, MenuItem, IconButton, Box,
    Chip, Typography,
    Grid2
} from "@mui/material";
import RobotIcon from "@mui/icons-material/SmartToy";
import ChipIcon from "@mui/icons-material/Memory";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import EmojiObjectsIcon from "@mui/icons-material/EmojiObjects";
import { Accordion, AccordionSummary, AccordionDetails } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import DeleteIcon from "@mui/icons-material/Delete";
import { useTranslation } from "react-i18next";
import { useCreateAgentMutation } from "../../slices/chatApi";
import { CreateAgentRequest } from "../../slices/chatApiStructures";
import { useToast } from "../ToastProvider";
import { useForm, Controller, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { createAgentSchema } from "./agentSchema";

interface CreateAgentModalProps {
    open: boolean;
    onClose: () => void;
    onCreated: () => void;
}

export const CreateAgentModal = ({ open, onClose, onCreated }: CreateAgentModalProps) => {
    const { t } = useTranslation();
    const { showError } = useToast();
    const [createAgent] = useCreateAgentMutation();
    const [customTag, setCustomTag] = useState("");
    const schema = createAgentSchema(t);
    const {
        control,
        handleSubmit,
        setValue,
        watch,
        reset,
        formState: { errors, isSubmitting },
    } = useForm<z.infer<typeof schema>>({
        resolver: zodResolver(schema),
        defaultValues: {
            name: "",
            nickname: "",
            description: "",
            role: "",
            base_prompt: "",
            icon: "Robot",
            agent_type: "mcp",
            categories: [],
            mcp_servers: [{ name: "", url: "", transport: "sse", sse_read_timeout: 30 }],
        },
    });

    const { fields, append, remove } = useFieldArray({
        control,
        name: "mcp_servers",
    });

    const onSubmit = async (data: z.infer<typeof schema>) => {
        try {
            await createAgent(data).unwrap();
            onCreated();
            reset();
        } catch (error) {
            console.error("Error creating agent:", error);
            showError({
                summary: t("agentHub.errors.creationFailedSummary"),
                detail: error?.data?.detail || t("agentHub.errors.creationFailedDetailFallback"),
            });
        }
    };

    const tags = watch("categories") || [];
    const agentType = watch("agent_type");

    const toggleTag = (tag: string) => {
        const newTags = tags.includes(tag)
            ? tags.filter((t) => t !== tag)
            : [...tags, tag];
        setValue("categories", newTags);
    };

    const TAG_GROUPS = {
        function: { tags: ["qa", "search", "audit", "dashboard", "monitoring", "retrieval", "forecasting", "summarization"], color: "success" },
        domain: { tags: ["ops", "security", "management", "finance", "legal", "compliance", "team", "data", "devops"], color: "warning" },
        behavior: { tags: ["expert", "planner", "tooluser", "chatbot", "sandbox"], color: "secondary" },
    };

    const getTagColor = (tag: string): any => {
        for (const group of Object.values(TAG_GROUPS)) {
            if (group.tags.includes(tag)) return group.color;
        }
        return "primary";
    };

    const iconOptions = [
        { label: "Robot", icon: <RobotIcon fontSize="small" /> },
        { label: "Chip", icon: <ChipIcon fontSize="small" /> },
        { label: "AutoAwesome", icon: <AutoAwesomeIcon fontSize="small" /> },
        { label: "EmojiObjects", icon: <EmojiObjectsIcon fontSize="small" /> },
    ];

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
            <DialogTitle>{t("agentHub.create")}</DialogTitle>
            <DialogContent dividers sx={{ px: 4 }}>
                <form onSubmit={handleSubmit(onSubmit)}>
                    <Grid2 container spacing={2}>
                        {["name", "nickname", "description", "role"].map((field) => (
                            <Grid2 key={field} size={{ xs: 12, sm: 6 }}>
                                <Controller
                                    name={field as keyof CreateAgentRequest}
                                    control={control}
                                    render={({ field: controllerField }) => (
                                        <TextField
                                            fullWidth
                                            size="small"
                                            label={t(`agentHub.fields.${field}`, field)}
                                            error={!!errors[field as keyof typeof errors]}
                                            helperText={errors[field as keyof typeof errors]?.message as string}
                                            {...controllerField}
                                        />
                                    )}
                                />
                            </Grid2>

                        ))}

                        {/* Tag Chips */}
                        <Grid2 size={12}>
                            <Typography variant="subtitle2" sx={{ mb: 1 }}>{t("agentHub.fields.tags", "Tags")}</Typography>
                            <Box display="flex" flexWrap="wrap" gap={1} mb={2}>
                                {tags.map((tag) => (
                                    <Chip
                                        key={tag}
                                        label={tag}
                                        size="small"
                                        color={getTagColor(tag)}
                                        onDelete={() => toggleTag(tag)}
                                    />
                                ))}
                            </Box>
                            <Grid2 container spacing={2} sx={{ pl: 3 }}>
                                <Grid2 size={{ xs: 12, sm: 6 }}>
                                    <Accordion disableGutters square sx={{
                                        height: 40, minHeight: 40, border: 1, borderColor: "divider", position: "relative",
                                        "& .MuiAccordionSummary-root": { minHeight: 40, padding: "0 8px" },
                                        "& .MuiAccordionSummary-content": { margin: 0 },
                                        "& .MuiAccordionDetails-root": {
                                            position: "absolute", top: 40, left: 0, width: "100%", zIndex: 10,
                                            bgcolor: "background.paper", boxShadow: 3, border: 1, borderTop: "none",
                                            maxHeight: 200, overflowY: "auto", p: 1,
                                        }
                                    }}>
                                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                            <Typography variant="body2">{t("agentHub.fields.selectFromPredefined", "Select from predefined tags")}</Typography>
                                        </AccordionSummary>
                                        <AccordionDetails>
                                            <Box display="flex" flexWrap="wrap" gap={1}>
                                                {Object.values(TAG_GROUPS).flatMap(group =>
                                                    group.tags.map(tag => (
                                                        <Chip
                                                            key={tag}
                                                            label={tag}
                                                            size="small"
                                                            color={getTagColor(tag)}
                                                            variant={tags.includes(tag) ? "filled" : "outlined"}
                                                            onClick={() => toggleTag(tag)}
                                                        />
                                                    ))
                                                )}
                                            </Box>
                                        </AccordionDetails>
                                    </Accordion>
                                </Grid2>
                                <Grid2 size={{ xs: 12, sm: 6 }}>
                                    <TextField
                                        fullWidth
                                        size="small"
                                        label={t("agentHub.fields.custom_tag", "Add custom tag")}
                                        value={customTag}
                                        onChange={(e) => setCustomTag(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter" && customTag.trim()) {
                                                e.preventDefault();
                                                if (!tags.includes(customTag.trim())) {
                                                    setValue("categories", [...tags, customTag.trim()]);
                                                }
                                                setCustomTag("");
                                            }
                                        }}
                                        placeholder={t("agentHub.fields.custom_tag_placeholder", "Press Enter to add")}
                                    />
                                </Grid2>
                            </Grid2>
                        </Grid2>

                        <Grid2 size={12}>
                            <Controller
                                name="base_prompt"
                                control={control}
                                render={({ field }) => (
                                    <TextField
                                        fullWidth
                                        multiline
                                        minRows={5}
                                        maxRows={20}
                                        size="small"
                                        label={t("agentHub.fields.base_prompt", "Base Prompt")}
                                        {...field}
                                    />
                                )}
                            />
                        </Grid2>

                        <Grid2 size={{ xs: 12, sm: 6 }}>
                            <Controller
                                name="agent_type"
                                control={control}
                                render={({ field }) => (
                                    <TextField select fullWidth size="small" label={t("agentHub.fields.agent_type")}{...field}>
                                        {schema.shape.agent_type.options.map((type) => (
                                            <MenuItem key={type} value={type}>{type}</MenuItem>
                                        ))}
                                    </TextField>
                                )}
                            />
                        </Grid2>

                        <Grid2 size={{ xs: 12, sm: 6 }}>
                            <Controller
                                name="icon"
                                control={control}
                                render={({ field }) => (
                                    <TextField select fullWidth size="small" label={t("agentHub.fields.icon")} {...field}>
                                        {iconOptions.map(({ label, icon }) => (
                                            <MenuItem key={label} value={label}>
                                                <Box display="flex" alignItems="center" gap={1}>{icon}{label}</Box>
                                            </MenuItem>
                                        ))}
                                    </TextField>
                                )}
                            />
                        </Grid2>

                        {agentType === "mcp" && (
                            <>
                                <Grid2 size={12}>
                                    <Typography fontWeight="bold">{t("agentHub.fields.mcp_servers")}</Typography>
                                </Grid2>

                                {fields.map((field, index) => (
                                    <Grid2 container spacing={1} key={field.id} wrap="nowrap" alignItems="center">
                                        <Grid2 sx={{ width: 150 }}>
                                            <Controller
                                                name={`mcp_servers.${index}.name`}
                                                control={control}
                                                render={({ field }) => (
                                                    <TextField
                                                        fullWidth
                                                        size="small"
                                                        label={t("agentHub.fields.mcp_server.name")}
                                                        error={!!errors.mcp_servers?.[index]?.name}
                                                        helperText={errors.mcp_servers?.[index]?.name?.message}
                                                        {...field}
                                                    />
                                                )}
                                            />
                                        </Grid2>

                                        <Grid2 sx={{ flexGrow: 1 }}>
                                            <Controller
                                                name={`mcp_servers.${index}.url`}
                                                control={control}
                                                render={({ field }) => (
                                                    <TextField
                                                        fullWidth
                                                        size="small"
                                                        label={t("agentHub.fields.mcp_server.url")}
                                                        error={!!errors.mcp_servers?.[index]?.url}
                                                        helperText={errors.mcp_servers?.[index]?.url?.message}
                                                        {...field}
                                                    />
                                                )}
                                            />
                                        </Grid2>

                                        <Grid2 sx={{ width: 140 }}>
                                            <Controller
                                                name={`mcp_servers.${index}.transport`}
                                                control={control}
                                                render={({ field }) => (
                                                    <TextField
                                                        select
                                                        fullWidth
                                                        size="small"
                                                        label={t("agentHub.fields.mcp_server.transport")}
                                                        error={!!errors.mcp_servers?.[index]?.transport}
                                                        helperText={errors.mcp_servers?.[index]?.transport?.message}
                                                        {...field}
                                                    >
                                                        {(schema.shape.mcp_servers.unwrap() as z.ZodArray<any>).element.shape.transport.options.map((opt) => (
                                                            <MenuItem key={opt} value={opt}>
                                                                {opt}
                                                            </MenuItem>
                                                        ))}
                                                    </TextField>
                                                )}
                                            />
                                        </Grid2>

                                        <Grid2 sx={{ width: 100 }}>
                                            <Controller
                                                name={`mcp_servers.${index}.sse_read_timeout`}
                                                control={control}
                                                render={({ field }) => (
                                                    <TextField
                                                        type="number"
                                                        fullWidth
                                                        size="small"
                                                        label={t("agentHub.fields.mcp_server.timeout")}
                                                        error={!!errors.mcp_servers?.[index]?.sse_read_timeout}
                                                        helperText={errors.mcp_servers?.[index]?.sse_read_timeout?.message}
                                                        inputProps={{ min: 0, step: 1 }}
                                                        value={field.value ?? ""}
                                                        onChange={(e) => {
                                                            const input = e.target as HTMLInputElement;
                                                            field.onChange(input.value === "" ? undefined : input.valueAsNumber);
                                                        }}
                                                    />
                                                )}
                                            />
                                        </Grid2>
                                        <Grid2>
                                            <IconButton onClick={() => remove(index)} size="small">
                                                <DeleteIcon />
                                            </IconButton>
                                        </Grid2>
                                    </Grid2>
                                ))}

                                <Grid2 size={12}>
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        onClick={() => append({ name: "", url: "", transport: "sse" })}
                                    >
                                        {t("agentHub.actions.add_mcp_server", "+ Add MCP Server")}
                                    </Button>
                                </Grid2>
                            </>
                        )}
                    </Grid2>
                    <DialogActions>
                        <Button size="small" onClick={onClose}>{t("dialogs.cancel", "Cancel")}</Button>
                        <Button size="small" type="submit" disabled={isSubmitting} variant="contained">
                            {t("dialogs.create.confirm", "Create")}
                        </Button>
                    </DialogActions>
                </form>
            </DialogContent>
        </Dialog>
    );
};
