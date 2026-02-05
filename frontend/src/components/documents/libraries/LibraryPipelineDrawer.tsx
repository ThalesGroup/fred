import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import SchemaOutlinedIcon from "@mui/icons-material/SchemaOutlined";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Drawer,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useToast } from "../../../components/ToastProvider";
import { SimpleTooltip } from "../../../shared/ui/tooltips/Tooltips";
import {
  AvailableProcessorsResponse,
  LibraryProcessorConfig,
  ProcessorConfig,
  useAssignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPostMutation,
  useListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetQuery,
  useRegisterProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPostMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

type PipelineStep = {
  id: string;
  classPath: string;
};

type PipelineInfo = {
  name: string;
  is_default_for_library: boolean;
  input_processors: ProcessorConfig[];
  output_processors: ProcessorConfig[];
  library_output_processors: LibraryProcessorConfig[];
};

export interface LibraryPipelineDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  libraryTagId: string | null;
  libraryLabel: string | null;
}

const buildKey = (prefix: string, classPath: string) => `${prefix}::${classPath}`;

const parseProcessorPath = (
  classPath: string,
): { folder: string | null; module: string | null; humanClass: string } => {
  const parts = classPath.split(".");
  if (parts.length < 3) {
    const className = parts[parts.length - 1] || classPath;
    const humanClass = className.replace(/([a-z0-9])([A-Z])/g, "$1 $2").trim();
    return { folder: null, module: null, humanClass: humanClass || className };
  }
  const className = parts[parts.length - 1] || "";
  const moduleName = parts[parts.length - 2] || "";
  const folderName = parts[parts.length - 3] || "";
  const humanClass = className.replace(/([a-z0-9])([A-Z])/g, "$1 $2").trim();
  return {
    folder: folderName,
    module: moduleName,
    humanClass: humanClass || className,
  };
};

const ProcessorLabel: React.FC<{ classPath: string }> = ({ classPath }) => {
  const { folder, module, humanClass } = parseProcessorPath(classPath);

  if (!folder || !module) {
    return (
      <Typography variant="body2" sx={{ fontSize: 13 }}>
        {humanClass}
      </Typography>
    );
  }

  return (
    <Box display="flex" flexDirection="column">
      <Typography variant="body2" sx={{ fontSize: 13, fontWeight: 500 }}>
        {humanClass}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {folder}/{module}
      </Typography>
    </Box>
  );
};

const ProcessorOption: React.FC<{ classPath: string; description?: string | null }> = ({ classPath, description }) => (
  <Stack direction="row" spacing={1} alignItems="flex-start">
    <Box flex={1} minWidth={0}>
      <ProcessorLabel classPath={classPath} />
    </Box>
    {description ? (
      <SimpleTooltip title={description}>
        <InfoOutlinedIcon sx={{ fontSize: 18, mt: 0.25, color: "text.secondary" }} />
      </SimpleTooltip>
    ) : null}
  </Stack>
);

export const LibraryPipelineDrawer: React.FC<LibraryPipelineDrawerProps> = ({
  isOpen,
  onClose,
  libraryTagId,
  libraryLabel,
}) => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();

  const [available, setAvailable] = useState<AvailableProcessorsResponse | null>(null);
  const [extensions, setExtensions] = useState<string[]>([]);
  const [selectedExt, setSelectedExt] = useState<string>(".pdf");
  const [stepsByExt, setStepsByExt] = useState<Record<string, PipelineStep[]>>({});
  const [inputByExt, setInputByExt] = useState<Record<string, string>>({});
  const [librarySteps, setLibrarySteps] = useState<PipelineStep[]>([]);
  const [pipelineName, setPipelineName] = useState<string | null>(null);
  const [pipelineIsDefault, setPipelineIsDefault] = useState<boolean>(false);
  const [helpOpen, setHelpOpen] = useState<boolean>(false);

  const { data: availableFromApi, isLoading: isLoadingAvailable } =
    useListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetQuery(undefined, {
      skip: !isOpen,
    });

  const [registerPipeline, { isLoading: isRegistering }] =
    useRegisterProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPostMutation();
  const [assignPipeline, { isLoading: isAssigning }] =
    useAssignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPostMutation();

  const loading = isLoadingAvailable || isRegistering || isAssigning;

  // Fetch available processors when opened
  useEffect(() => {
    if (!isOpen) return;
    if (!availableFromApi) return;

    try {
      setAvailable(availableFromApi);
      const exts = Array.from(
        new Set([
          ...(availableFromApi.input_processors || []).map((p) => p.prefix),
          ...(availableFromApi.output_processors || []).map((p) => p.prefix),
        ]),
      ).sort();
      setExtensions(exts);
      if (exts.length && !exts.includes(selectedExt)) {
        setSelectedExt(exts[0]);
      }
      const init: Record<string, PipelineStep[]> = {};
      exts.forEach((ext) => {
        init[ext] = [];
      });
      setStepsByExt(init);

      // Initialise input processor selection per extension with the first configured one
      const inputInit: Record<string, string> = {};
      for (const ip of availableFromApi.input_processors || []) {
        const key = ip.prefix.toLowerCase();
        if (!inputInit[key]) {
          inputInit[key] = ip.class_path;
        }
      }
      setInputByExt(inputInit);
      setLibrarySteps([]);
    } catch (err: any) {
      console.error("Failed to initialise pipeline editor:", err);
      showError({
        summary: t("documentLibrary.pipeline.loadErrorSummary") || "Failed to load processors",
        detail: err?.message || String(err),
      });
    }
  }, [availableFromApi, isOpen, showError, t]);

  // Fetch existing pipeline for this library (if any) and pre-fill selections
  useEffect(() => {
    if (!isOpen) return;
    if (!libraryTagId) return;
    if (!available) return;

    const controller = new AbortController();

    const fetchPipeline = async () => {
      try {
        const res = await fetch(`/knowledge-flow/v1/processing/pipelines/library/${encodeURIComponent(libraryTagId)}`, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          signal: controller.signal,
        });
        if (!res.ok) {
          // No pipeline configured yet → keep defaults
          return;
        }
        const data: PipelineInfo = await res.json();
        setPipelineName(data.name);
        setPipelineIsDefault(data.is_default_for_library);

        // Build steps per extension from output_processors
        const byExtSteps: Record<string, PipelineStep[]> = {};
        (available.output_processors || []).forEach((p) => {
          const key = p.prefix.toLowerCase();
          if (!byExtSteps[key]) {
            byExtSteps[key] = [];
          }
        });
        (data.output_processors || []).forEach((p, idx) => {
          const key = p.prefix.toLowerCase();
          if (!byExtSteps[key]) {
            byExtSteps[key] = [];
          }
          byExtSteps[key].push({
            id: buildKey(key, `${p.class_path}-${idx}`),
            classPath: p.class_path,
          });
        });
        setStepsByExt(byExtSteps);

        const libraryStepsFromApi: PipelineStep[] = (data.library_output_processors || []).map((p, idx) => ({
          id: buildKey("library", `${p.class_path}-${idx}`),
          classPath: p.class_path,
        }));
        setLibrarySteps(libraryStepsFromApi);

        // Input processors per extension
        const byExtInput: Record<string, string> = { ...inputByExt };
        (data.input_processors || []).forEach((p) => {
          const key = p.prefix.toLowerCase();
          byExtInput[key] = p.class_path;
        });
        setInputByExt(byExtInput);
      } catch (err) {
        if ((err as any)?.name === "AbortError") return;
        console.error("Failed to fetch pipeline for library:", err);
      }
    };

    void fetchPipeline();

    return () => controller.abort();
  }, [available, isOpen, libraryTagId]);

  const outputOptionsByExt = useMemo(() => {
    const map: Record<string, ProcessorConfig[]> = {};
    if (!available) return map;
    for (const p of available.output_processors || []) {
      const key = p.prefix.toLowerCase();
      if (!map[key]) map[key] = [];
      map[key].push(p);
    }
    // Stable sort by class_path for predictable UX
    Object.keys(map).forEach((k) => map[k].sort((a, b) => a.class_path.localeCompare(b.class_path)));
    return map;
  }, [available]);

  const inputOptionsByExt = useMemo(() => {
    const map: Record<string, ProcessorConfig[]> = {};
    if (!available) return map;
    for (const p of available.input_processors || []) {
      const key = p.prefix.toLowerCase();
      if (!map[key]) map[key] = [];
      map[key].push(p);
    }
    Object.keys(map).forEach((k) => map[k].sort((a, b) => a.class_path.localeCompare(b.class_path)));
    return map;
  }, [available]);

  const libraryOutputOptions = useMemo<LibraryProcessorConfig[]>(() => {
    return available?.library_output_processors || [];
  }, [available]);

  const outputLookup = useMemo(() => {
    const map = new Map<string, ProcessorConfig>();
    (available?.output_processors || []).forEach((p) => map.set(p.class_path, p));
    return map;
  }, [available]);

  const inputLookup = useMemo(() => {
    const map = new Map<string, ProcessorConfig>();
    (available?.input_processors || []).forEach((p) => map.set(p.class_path, p));
    return map;
  }, [available]);

  const libraryLookup = useMemo(() => {
    const map = new Map<string, LibraryProcessorConfig>();
    (available?.library_output_processors || []).forEach((p) => map.set(p.class_path, p));
    return map;
  }, [available]);

  const currentSteps = stepsByExt[selectedExt] || [];
  const existingOutputClassPaths = new Set(currentSteps.map((s) => s.classPath));
  const libraryClassPaths = new Set(librarySteps.map((s) => s.classPath));

  const handleAddStep = () => {
    const opts = outputOptionsByExt[selectedExt] || [];
    const first = opts.find((p) => !existingOutputClassPaths.has(p.class_path));
    if (!first) return;
    const id = buildKey(selectedExt, `${first.class_path}-${Date.now()}-${currentSteps.length}`);
    const next: PipelineStep = { id, classPath: first.class_path };
    setStepsByExt((prev) => ({
      ...prev,
      [selectedExt]: [...(prev[selectedExt] || []), next],
    }));
  };

  const handleChangeStep = (stepId: string, newClassPath: string) => {
    setStepsByExt((prev) => ({
      ...prev,
      [selectedExt]: (prev[selectedExt] || []).map((s) => (s.id === stepId ? { ...s, classPath: newClassPath } : s)),
    }));
  };

  const handleRemoveStep = (stepId: string) => {
    setStepsByExt((prev) => ({
      ...prev,
      [selectedExt]: (prev[selectedExt] || []).filter((s) => s.id !== stepId),
    }));
  };

  const handleAddLibraryProcessor = () => {
    if (!libraryOutputOptions.length) return;
    const first = libraryOutputOptions.find((p) => !libraryClassPaths.has(p.class_path));
    if (!first) return;
    setLibrarySteps((prev) => {
      const id = buildKey("library", `${first.class_path}-${Date.now()}-${prev.length}`);
      return [...prev, { id, classPath: first.class_path }];
    });
  };

  const handleChangeLibraryProcessor = (stepId: string, newClassPath: string) => {
    setLibrarySteps((prev) => prev.map((s) => (s.id === stepId ? { ...s, classPath: newClassPath } : s)));
  };

  const handleRemoveLibraryProcessor = (stepId: string) => {
    setLibrarySteps((prev) => prev.filter((s) => s.id !== stepId));
  };

  const handleSave = async () => {
    if (!libraryTagId) {
      showError({
        summary: t("documentLibrary.pipeline.noLibrarySummary") || "No library selected",
        detail: t("documentLibrary.pipeline.noLibraryDetail") || "Please select a library first.",
      });
      return;
    }
    if (!available) return;

    try {
      // 1) Register pipeline definition
      const pipelineName = `library-${libraryTagId}`;
      const allSteps: ProcessorConfig[] = [];
      Object.entries(stepsByExt).forEach(([ext, steps]) => {
        steps.forEach((s) => {
          const candidate = outputLookup.get(s.classPath);
          allSteps.push({
            prefix: ext,
            class_path: s.classPath,
            description: candidate?.description,
          });
        });
      });

      if (!allSteps.length) {
        showError({
          summary: t("documentLibrary.pipeline.emptyPipelineSummary") || "Pipeline is empty",
          detail: t("documentLibrary.pipeline.emptyPipelineDetail") || "Add at least one processor.",
        });
        return;
      }

      const inputDefs: ProcessorConfig[] = Object.entries(inputByExt)
        .filter(([, classPath]) => !!classPath)
        .map(([prefix, class_path]) => ({
          prefix,
          class_path,
          description: inputLookup.get(class_path)?.description,
        }));
      const libraryDefs: LibraryProcessorConfig[] = librarySteps.map((step) => {
        const candidate = libraryLookup.get(step.classPath);
        return {
          class_path: step.classPath,
          description: candidate?.description,
        };
      });

      await registerPipeline({
        processingPipelineDefinition: {
          name: pipelineName,
          input_processors: inputDefs,
          output_processors: allSteps,
          library_output_processors: libraryDefs,
        },
      }).unwrap();

      // 2) Bind pipeline to library tag id
      await assignPipeline({
        pipelineAssignment: {
          library_tag_id: libraryTagId,
          pipeline_name: pipelineName,
        },
      }).unwrap();

      showSuccess({
        summary: t("documentLibrary.pipeline.savedSummary") || "Pipeline saved",
        detail:
          t("documentLibrary.pipeline.savedDetail", { name: libraryLabel || libraryTagId }) ||
          "Processing pipeline has been configured for this library.",
      });

      onClose();
    } catch (err: any) {
      console.error("Failed to save pipeline:", err);
      showError({
        summary: t("documentLibrary.pipeline.saveErrorSummary") || "Failed to save pipeline",
        detail: err?.message || String(err),
      });
    }
  };

  const handleClose = () => {
    setStepsByExt({});
    setInputByExt({});
    setSelectedExt(".pdf");
    setLibrarySteps([]);
    onClose();
  };

  return (
    <Drawer
      anchor="right"
      open={isOpen}
      onClose={handleClose}
      PaperProps={{
        sx: {
          width: { xs: "100%", sm: 720 },
          p: 3,
        },
      }}
    >
      <Box display="flex" alignItems="center" justifyContent="space-between" gap={1} mb={2}>
        <Box display="flex" alignItems="center" gap={1}>
          <SchemaOutlinedIcon color="primary" />
          <Typography variant="h5" fontWeight="bold">
            {t("documentLibrary.pipeline.title") || "Configure Processing Pipeline"}
          </Typography>
        </Box>
        <Button size="small" variant="outlined" startIcon={<InfoOutlinedIcon />} onClick={() => setHelpOpen(true)}>
          {t("documentLibrary.pipeline.helpButton") || "How it works"}
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" mb={2}>
        {t("documentLibrary.pipeline.description") ||
          "Choose the chain of processors to apply for each file type in this library."}
      </Typography>

      <Stack direction="row" spacing={1} alignItems="center" mb={2}>
        <Typography variant="subtitle2" color="text.secondary">
          {t("documentLibrary.pipeline.library") || "Library"}
        </Typography>
        <Chip label={libraryLabel || libraryTagId || "-"} size="small" />
        {pipelineName && (
          <Chip
            label={
              pipelineIsDefault
                ? `${t("documentLibrary.pipeline.currentDefault") || "Pipeline"}: ${pipelineName} (${
                    t("documentLibrary.pipeline.defaultTag") || "default"
                  })`
                : `${t("documentLibrary.pipeline.current") || "Pipeline"}: ${pipelineName}`
            }
            size="small"
            color={pipelineIsDefault ? "default" : "primary"}
            variant={pipelineIsDefault ? "outlined" : "filled"}
          />
        )}
      </Stack>

      {/* Extension selector */}
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel>{t("documentLibrary.pipeline.extensionLabel") || "File extension"}</InputLabel>
        <Select
          label={t("documentLibrary.pipeline.extensionLabel") || "File extension"}
          value={selectedExt}
          onChange={(e) => setSelectedExt(e.target.value as string)}
          disabled={loading || !extensions.length}
        >
          {extensions.map((ext) => (
            <MenuItem key={ext} value={ext}>
              {ext}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {/* Extension quick-switch chips with step counts */}
      <Stack direction="row" spacing={1} flexWrap="wrap" mb={2}>
        {extensions.map((ext) => {
          const count = (stepsByExt[ext] || []).length;
          const label = count > 0 ? `${ext} (${count})` : ext;
          return (
            <Chip
              key={ext}
              label={label}
              size="small"
              color={ext === selectedExt ? "primary" : "default"}
              onClick={() => setSelectedExt(ext)}
              sx={{ mb: 0.5 }}
            />
          );
        })}
      </Stack>

      {/* Input processor selector for the selected extension */}
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel>{t("documentLibrary.pipeline.inputLabel") || "Input processor"}</InputLabel>
        <Select
          label={t("documentLibrary.pipeline.inputLabel") || "Input processor"}
          value={inputByExt[selectedExt] || ""}
          onChange={(e) =>
            setInputByExt((prev) => ({
              ...prev,
              [selectedExt]: e.target.value as string,
            }))
          }
          disabled={loading || !(inputOptionsByExt[selectedExt] || []).length}
        >
          {(inputOptionsByExt[selectedExt] || []).map((p) => (
            <MenuItem key={buildKey(p.prefix, p.class_path)} value={p.class_path}>
              <ProcessorOption classPath={p.class_path} description={p.description} />
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      {/* Pipeline steps for selected extension */}
      <Box mb={2}>
        <Typography variant="subtitle2" gutterBottom>
          {t("documentLibrary.pipeline.stepsLabel") || "Processors chain"}
        </Typography>
        <Stack spacing={1}>
          {currentSteps.map((step, idx) => {
            const opts = outputOptionsByExt[selectedExt] || [];
            return (
              <Stack key={step.id} direction="row" spacing={1} alignItems="center">
                <Typography variant="body2" color="text.secondary" sx={{ minWidth: 40 }}>
                  {idx + 1}.
                </Typography>
                <FormControl fullWidth size="small">
                  <Select value={step.classPath} onChange={(e) => handleChangeStep(step.id, e.target.value as string)}>
                    {opts.map((p) => (
                      <MenuItem key={buildKey(p.prefix, p.class_path)} value={p.class_path}>
                        <ProcessorOption classPath={p.class_path} description={p.description} />
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Button variant="outlined" size="small" color="error" onClick={() => handleRemoveStep(step.id)}>
                  {t("documentLibrary.pipeline.removeStep") || "Remove"}
                </Button>
              </Stack>
            );
          })}
          <Button
            variant="outlined"
            size="small"
            onClick={handleAddStep}
            disabled={loading || !(outputOptionsByExt[selectedExt] || []).length}
          >
            {t("documentLibrary.pipeline.addStep") || "Add processor"}
          </Button>
        </Stack>
      </Box>

      {/* Library-level processors (run once per library) */}
      <Box mb={2}>
        <Typography variant="subtitle2" gutterBottom>
          {t("documentLibrary.pipeline.libraryProcessors") || "Library processors"}
        </Typography>
        <Typography variant="body2" color="text.secondary" mb={1}>
          {t("documentLibrary.pipeline.libraryProcessorsHelper") ||
            "These processors run at the library level, after documents have been processed."}
        </Typography>
        <Stack spacing={1}>
          {librarySteps.map((step, idx) => (
            <Stack key={step.id} direction="row" spacing={1} alignItems="center">
              <Typography variant="body2" color="text.secondary" sx={{ minWidth: 40 }}>
                {idx + 1}.
              </Typography>
              <FormControl fullWidth size="small">
                <Select
                  value={step.classPath}
                  onChange={(e) => handleChangeLibraryProcessor(step.id, e.target.value as string)}
                >
                  {libraryOutputOptions.map((p) => (
                    <MenuItem key={p.class_path} value={p.class_path}>
                      <ProcessorOption classPath={p.class_path} description={p.description} />
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="outlined"
                size="small"
                color="error"
                onClick={() => handleRemoveLibraryProcessor(step.id)}
              >
                {t("documentLibrary.pipeline.removeStep") || "Remove"}
              </Button>
            </Stack>
          ))}
          <Button
            variant="outlined"
            size="small"
            onClick={handleAddLibraryProcessor}
            disabled={loading || !libraryOutputOptions.length}
          >
            {t("documentLibrary.pipeline.addLibraryProcessor") || "Add library processor"}
          </Button>
          {!libraryOutputOptions.length && (
            <Typography variant="caption" color="text.secondary">
              {t("documentLibrary.pipeline.noLibraryProcessorAvailable") || "No library processors available."}
            </Typography>
          )}
        </Stack>
      </Box>

      <Box mt="auto" display="flex" justifyContent="space-between">
        <Button variant="outlined" onClick={handleClose}>
          {t("documentLibrary.pipeline.cancel") || "Cancel"}
        </Button>
        <Button variant="contained" color="primary" onClick={handleSave} disabled={loading}>
          {t("documentLibrary.pipeline.save") || "Save pipeline"}
        </Button>
      </Box>

      <Dialog open={helpOpen} onClose={() => setHelpOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("documentLibrary.pipeline.helpTitle") || "How pipelines work"}</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" paragraph>
            {t("documentLibrary.pipeline.helpIntro") ||
              "Pipelines let you decide which processors run on your documents and when."}
          </Typography>
          <Typography variant="subtitle2">
            {t("documentLibrary.pipeline.helpInputTitle") || "Input processors"}
          </Typography>
          <Typography variant="body2" color="text.secondary" paragraph>
            {t("documentLibrary.pipeline.helpInputBody") ||
              "Turn raw files into normalized previews (Markdown or tables) per file type."}
          </Typography>
          <Typography variant="subtitle2">
            {t("documentLibrary.pipeline.helpOutputTitle") || "Output processors"}
          </Typography>
          <Typography variant="body2" color="text.secondary" paragraph>
            {t("documentLibrary.pipeline.helpOutputBody") ||
              "Post-process each document (vectorize, tabular load, summarize). They can run right after ingestion or later from Operations."}
          </Typography>
          <Typography variant="subtitle2">
            {t("documentLibrary.pipeline.helpLibraryTitle") || "Library output processors"}
          </Typography>
          <Typography variant="body2" color="text.secondary" paragraph>
            {t("documentLibrary.pipeline.helpLibraryBody") ||
              "Run once per library to build shared assets (e.g., library TOC). They run from the Operations tab, not during ingestion."}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelpOpen(false)}>{t("documentLibrary.pipeline.close") || "Close"}</Button>
        </DialogActions>
      </Dialog>
    </Drawer>
  );
};
