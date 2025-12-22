// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  IconButton,
  InputLabel,
  ListItemText,
  MenuItem,
  OutlinedInput,
  Paper,
  Select,
  SelectChangeEvent,
  Typography,
  Divider,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import { useContext, useEffect, useRef, useState } from "react";
import AnalyticsIcon from "@mui/icons-material/Analytics";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useLocalStorageState } from "../hooks/useLocalStorageState.ts";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import Graph3DView from "../components/graph/Graph3DView.tsx";
import {
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useProjectKnowledgeFlowV1ModelsUmapRefTagUidProjectPostMutation,
  useDeleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDeleteMutation,
  useTrainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPostMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { ApplicationContext } from "../app/ApplicationContextProvider.tsx";
import { usePointsSync } from "../components/graph/graphPoints";
import { buildChunkToDocMap, filterDeletableIds, removePointsByChunkIds } from "../components/graph/deletionUtils";
import SelectionPanel from "../components/graph/SelectionPanel";
import { useToast } from "../components/ToastProvider";

const PANEL_W = { xs: 300, sm: 340, md: 360 };

type PanelContentType = "actions" | null;

export default function GraphHub() {
  const { darkMode } = useContext(ApplicationContext);
  const { t } = useTranslation();
  const { showError } = useToast();
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [panelContentType, setPanelContentType] = useLocalStorageState<PanelContentType>(
    "chat.panelContentType",
    "actions",
  );
  const isPanelOpen = panelContentType !== null;

  const openPanel = (type: PanelContentType) => {
    setPanelContentType(panelContentType === type ? null : type);
  };
  const closePanel = () => setPanelContentType(null);

  const openConversationsPanel = () => openPanel("actions");

  // Tags for documents
  const { data: tagsData } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" });
  const [selectedTagId, setSelectedTagId] = useState<string | "">("");
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([]);
  
  // UMAP projection for a whole tag
  const [projectUmap, { data: projection, isLoading: isProjecting, error: projectError, reset: resetProjection }] =
    useProjectKnowledgeFlowV1ModelsUmapRefTagUidProjectPostMutation();

  // Selected nodes from the 3D graph
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Local points sync and fit control
  const { points, setPoints, fitVersion } = usePointsSync(projection?.graph_points, isProjecting);

  const handleSelectTag = (e: SelectChangeEvent<string>) => {
    setSelectedTagId(e.target.value as string);
    // Clear graph when reference library changes
    resetProjection();
    setPoints([]);
    setSelectedIds([]);
  };
  
  const handleSelectTagIds = (event: SelectChangeEvent<typeof selectedTagIds>) => {
    const value = event.target.value;
    setSelectedTagIds(typeof value === "string" ? value.split(",") : value);
    // Clear graph when libraries selection changes
    resetProjection();
    setPoints([]);
    setSelectedIds([]);
  };

  // Track if error has been shown to avoid duplicates
  const errorShownRef = useRef(false);

  // Show error toast when projection fails (only once)
  useEffect(() => {
    if (projectError && !errorShownRef.current) {
      errorShownRef.current = true;
      const errorData = (projectError as any)?.data;
      const detail = errorData?.detail || (projectError as any)?.message || String(projectError);
      
      // Check if it's a "model not found" error
      let summary = t("graphHub.umapError", "Error with projection");
      let message = detail;
      
      if (typeof detail === 'string' && detail.includes('Object not found') && detail.includes('model.umap')) {
        summary = t("graphHub.modelNotFoundError", "Model not found");
        message = t("graphHub.modelNotFoundDetail", "The UMAP model has not been trained yet. Please train the model first.");
      }
      
      showError({
        summary,
        detail: message,
      });
    }
  }, [projectError, showError, t]);

  // Reset error flag when starting a new projection
  useEffect(() => {
    if (isProjecting) {
      errorShownRef.current = false;
    }
  }, [isProjecting]);

  // Delete chunk mutation
  const [deleteChunk, { isLoading: isDeleting }] =
    useDeleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDeleteMutation();

  // Train UMAP model for selected tag
  const [trainUmap, { isLoading: isTraining }] = useTrainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPostMutation();

  const handleRefresh = () => {
    if (selectedTagId && selectedTagIds.length > 0) {
      // Clear current graph data and selection immediately
      resetProjection();
      setPoints([]);
      setSelectedIds([]);
      // Use the reference library model (selectedTagId) to project the selected libraries
      projectUmap({ 
        refTagUid: selectedTagId, 
        projectRequest: { 
          tag_uids: selectedTagIds 
        } 
      });
    }
  };

  const handleTrain = async () => {
    if (!selectedTagId || isTraining) return;
    // Clear current graph data and selection immediately
    resetProjection();
    setPoints([]);
    setSelectedIds([]);
    try {
      await trainUmap({ tagId: selectedTagId }).unwrap();
      // After training completes, user can hit Show graph to project the new model
    } catch (e) {
      // Silently fail for now; could add snackbar later
    }
  };

  // Map chunk_uid -> document_uid for quick lookup when deleting
  const idToDocMap = buildChunkToDocMap(points);

  // Only keep ids that actually map to a document (i.e., real chunk_uids)
  const deletableIds = filterDeletableIds(selectedIds, idToDocMap);

  // Map chunk_uid -> text (from GraphPoint.metadata.text) to display in chunk accordion
  const idToTextMap = (points ?? []).reduce<Record<string, string>>((acc, p: any) => {
    const cid = p?.metadata?.chunk_uid ?? p?.chunk_uid;
    const text = p?.metadata?.text ?? p?.text;
    if (cid != null && typeof text === "string") acc[String(cid)] = text;
    return acc;
  }, {});

  const handleDeleteSelection = async () => {
    if (!deletableIds.length) return;
    try {
      // Pair chunkIds with their deletion promises to know which succeeded
      const tasks = deletableIds
        .map((chunkId) => {
          const documentUid = idToDocMap[chunkId];
          if (!documentUid) return null;
          return { chunkId, promise: deleteChunk({ documentUid, chunkId }).unwrap() };
        })
        .filter(Boolean) as { chunkId: string; promise: Promise<any> }[];
      if (tasks.length === 0) return;
      const results = await Promise.allSettled(tasks.map((t) => t.promise));
      // Collect successfully deleted ids and failed deletions
      const successfulIds = new Set<string>();
      let failedCount = 0;
      results.forEach((res, idx) => {
        if (res.status === "fulfilled") {
          successfulIds.add(tasks[idx].chunkId);
        } else {
          failedCount++;
        }
      });
      if (successfulIds.size > 0) {
        setPoints((prev) => removePointsByChunkIds(prev, successfulIds));
      }
      // Show a single error message if any deletions failed
      if (failedCount > 0) {
        showError({
          summary: t("graphHub.deletionError", "Error deleting chunks"),
          detail: t("graphHub.deletionErrorDetail", {
            failed: failedCount,
            total: tasks.length,
            defaultValue: `${failedCount} out of ${tasks.length} chunks could not be deleted`,
          }),
        });
      }
    } finally {
      // Clear selection regardless of partial failures
      setSelectedIds([]);
    }
  };

  const buttonContainerSx = {
    position: "absolute",
    top: 12,
    zIndex: 10,
    display: "flex",
    alignItems: "center",
    gap: 1,
    transition: (t) => t.transitions.create("left"), // Add transition for smooth movement

    // Conditional left position to move the buttons when the panel is open
    left: isPanelOpen
      ? {
          xs: `calc(${PANEL_W.xs}px + 12px)`,
          sm: `calc(${PANEL_W.sm}px + 12px)`,
          md: `calc(${PANEL_W.md}px + 12px)`,
        }
      : 12, // Original position when closed
  };

  return (
    <Box ref={containerRef} sx={{ height: "100vh", position: "relative", overflow: "hidden" }}>
      <Box sx={buttonContainerSx}>
        <IconButton
          color={panelContentType === "actions" ? "primary" : "default"}
          onClick={openConversationsPanel}
          title={t("graphHub.panelTitle", "Action")}
        >
          <AnalyticsIcon />
        </IconButton>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: isPanelOpen
            ? { xs: `${PANEL_W.xs}px 1fr`, sm: `${PANEL_W.sm}px 1fr`, md: `${PANEL_W.md}px 1fr` }
            : "0px 1fr",
          transition: (t) =>
            t.transitions.create("grid-template-columns", {
              duration: t.transitions.duration.standard,
              easing: t.transitions.easing.sharp,
            }),
          height: "100%",
        }}
      >
        {/* Side Panel */}
        <Paper
          square
          elevation={isPanelOpen ? 6 : 0}
          sx={{
            overflow: "hidden",
            borderRight: (t) => `1px solid ${t.palette.divider}`,
            bgcolor: (t) => t.palette.sidebar?.background ?? t.palette.background.paper,
            display: "flex",
            flexDirection: "column",
            pointerEvents: isPanelOpen ? "auto" : "none",
          }}
        >
          {/* Panel Header (Static top part) */}
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              px: 1,
              py: 1,
              borderBottom: (t) => `1px solid ${t.palette.divider}`,
              flex: "0 0 auto",
            }}
          >
            {/* Back Button */}
            <IconButton size="small" onClick={closePanel} sx={{ visibility: isPanelOpen ? "visible" : "hidden" }}>
              <ChevronLeftIcon fontSize="small" />
            </IconButton>

            {/* Title */}
          </Box>

          {/* Content Body (Takes the rest of the space) */}
          <Box
            sx={{
              flex: 1,
              minHeight: 0,
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 2 }}>
              <Typography variant="subtitle2">{t("graphHub.trainModelSection", "Train Model")}</Typography>
              <FormControl size="small" fullWidth>
                <InputLabel id="tag-select-label">{t("graphHub.selectLibrary", "Reference library")}</InputLabel>
                <Select
                  labelId="tag-select-label"
                  label={t("graphHub.selectLibrary", "Reference library")}
                  value={selectedTagId}
                  onChange={handleSelectTag}
                >
                  {(tagsData ?? []).map((tag) => (
                    <MenuItem key={tag.id} value={tag.id}>
                      {tag.path ? `${tag.path}/${tag.name}` : tag.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<AnalyticsIcon />}
                  onClick={handleTrain}
                  disabled={!selectedTagId || isTraining}
                >
                  {isTraining ? t("graphHub.training", "Training…") : t("graphHub.trainModel", "Train model")}
                </Button>
              </Box>

              <Divider sx={{ my: 1 }} />

              <Typography variant="subtitle2">{t("graphHub.showGraphSection", "Show Graph")}</Typography>
              <FormControl size="small" fullWidth>
                <InputLabel id="multi-tag-select-label">{t("graphHub.selectLibraries", "Libraries")}</InputLabel>
                <Select
                  labelId="multi-tag-select-label"
                  label={t("graphHub.selectLibraries", "Libraries")}
                  multiple
                  value={selectedTagIds}
                  onChange={handleSelectTagIds}
                  input={<OutlinedInput label={t("graphHub.selectLibraries", "Libraries")} />}
                  renderValue={(selected) => (
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                      {selected.map((tagId) => {
                        const tag = (tagsData ?? []).find((t) => t.id === tagId);
                        const label = tag ? (tag.path ? `${tag.path}/${tag.name}` : tag.name) : tagId;
                        return <Chip key={tagId} label={label} size="small" />;
                      })}
                    </Box>
                  )}
                >
                  {(tagsData ?? []).map((tag) => (
                    <MenuItem key={tag.id} value={tag.id}>
                      <ListItemText primary={tag.path ? `${tag.path}/${tag.name}` : tag.name} />
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<RefreshIcon />}
                  onClick={handleRefresh}
                  disabled={!selectedTagId || selectedTagIds.length === 0 || isProjecting || isDeleting || isTraining}
                >
                  {t("graphHub.refreshGraph", "Show graph")}
                </Button>
              </Box>
              
              {/* Separator and selection accordions are visible only when there is a selection */}
              {selectedIds.length > 0 && (
                <>
                  <Divider sx={{ my: 1 }} />
                  <SelectionPanel
                    idToDocMap={idToDocMap}
                    idToTextMap={idToTextMap}
                    selectedIds={selectedIds}
                    handleDeleteSelection={handleDeleteSelection}
                    isDeleting={isDeleting}
                    t={t as any}
                  />
                </>
              )}
            </Box>
          </Box>
        </Paper>

        {/* Main 3D Graph Area */}
        <Box sx={{ position: "relative", height: "100%", width: "100%", bgcolor: (t) => t.palette.background.default }}>
          {isProjecting && (
            <Box
              sx={{
                position: "absolute",
                inset: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 2,
              }}
            >
              <CircularProgress />
            </Box>
          )}
          <Box sx={{ position: "absolute", inset: 0 }}>
            <Graph3DView
              points={points}
              darkMode={darkMode}
              tagUid={selectedTagId || undefined}
              onSelectionChange={setSelectedIds}
              fitVersion={fitVersion}
              fitOnResize={false}
            />
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
