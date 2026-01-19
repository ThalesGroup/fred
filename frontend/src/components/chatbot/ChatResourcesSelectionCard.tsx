// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import {
  Box,
  Checkbox,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Radio,
  TextField,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Resource,
  ResourceKind,
  TagType,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface ResourceLibrariesSelectionCardProps {
  libraryType: TagType;
  selectedResourceIds: string[];
  setSelectedResourceIds: (ids: string[]) => void;
  selectionMode?: "single" | "multiple";
}

type Lib = Pick<TagWithItemsId, "id" | "name" | "path" | "description">;

export function ChatResourcesSelectionCard({
  libraryType,
  selectedResourceIds,
  setSelectedResourceIds,
  selectionMode = "single",
}: ResourceLibrariesSelectionCardProps) {
  const { t } = useTranslation();

  // Libraries (as groups to browse)
  const {
    data: tags = [],
    isLoading,
    isError,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    {
      type: libraryType,
    },
    { refetchOnMountOrArgChange: true },
  );

  // Fetch resources of that kind
  const resourceKind: ResourceKind | undefined = (() => {
    if (libraryType === "prompt") return "prompt" as ResourceKind;
    if (libraryType === "template") return "template" as ResourceKind;
    if (libraryType === "chat-context") return "chat-context" as ResourceKind;
    return undefined;
  })();

  const { data: fetchedResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery(
    { kind: resourceKind },
    { skip: !resourceKind, refetchOnMountOrArgChange: true },
  );

  const [searchQuery, setSearchQuery] = useState("");
  const [openMap, setOpenMap] = useState<Record<string, boolean>>({});

  const libs = useMemo<Lib[]>(
    () =>
      (tags as TagWithItemsId[])
        .map((x) => ({
          id: x.id,
          name: x.name,
          path: x.path ?? null,
          description: x.description ?? null,
        }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [tags],
  );

  // tagId -> resources[]
  const resourcesByTag = useMemo(() => {
    const map = new Map<string, Resource[]>();
    (fetchedResources as Resource[]).forEach((r) => {
      (r.library_tags ?? []).forEach((tagId) => {
        if (!map.has(tagId)) map.set(tagId, []);
        map.get(tagId)!.push(r);
      });
    });
    return map;
  }, [fetchedResources]);

  const filtered = useMemo(() => {
    const needle = searchQuery.trim().toLowerCase();
    return libs
      .map((lib) => {
        const contents = resourcesByTag.get(lib.id) ?? [];

        if (!needle) {
          return { lib, resources: contents };
        }

        const matchesLib =
          lib.name.toLowerCase().includes(needle) ||
          (lib.path ?? "").toLowerCase().includes(needle) ||
          (lib.description ?? "").toLowerCase().includes(needle);

        const matchedResources = contents.filter((resource) => {
          const name = resource.name?.toLowerCase() ?? "";
          const description = resource.description?.toLowerCase() ?? "";
          return name.includes(needle) || description.includes(needle);
        });

        if (!matchesLib && matchedResources.length === 0) {
          return null;
        }

        const resources = matchesLib && matchedResources.length === 0 ? contents : matchedResources;

        return { lib, resources };
      })
      .filter((entry): entry is { lib: Lib; resources: Resource[] } => entry !== null);
  }, [libs, resourcesByTag, searchQuery]);

  const isMultiSelect = selectionMode === "multiple";

  // --- single-select helpers ---
  const selectResource = (id: string) => {
    if (!isMultiSelect) {
      setSelectedResourceIds([id]);
      return;
    }

    const isAlreadySelected = selectedResourceIds.includes(id);
    const next = isAlreadySelected ? selectedResourceIds.filter((rid) => rid !== id) : [...selectedResourceIds, id];
    setSelectedResourceIds(next);
  };

  const toggleSelectResource = (id: string) => {
    selectResource(id);
  };

  const toggleOpen = (id: string) => setOpenMap((m) => ({ ...m, [id]: !m[id] }));

  const searchLabel = useMemo(() => {
    if (libraryType === "template") return t("chatbot.searchTemplateLibraries", "Search template libraries");
    if (libraryType === "chat-context") return t("chatbot.searchChatContextLibraries", "Search chat context libraries");
    return t("chatbot.searchPromptLibraries", "Search prompt libraries");
  }, [libraryType, t]);

  return (
    <Box
      sx={{
        width: "100%",
        maxWidth: 420,
        height: "min(70vh, 460px)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Search libraries */}
      <Box sx={{ mx: 2, mt: 2, mb: 1 }}>
        <TextField
          autoFocus
          size="small"
          fullWidth
          label={searchLabel}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </Box>

      {/* Body */}
      <Box sx={{ flex: 1, overflowY: "auto", overflowX: "hidden", px: 1, pb: 1.5 }}>
        {isLoading ? (
          <Typography variant="body2" sx={{ px: 2, py: 1, color: "text.secondary" }}>
            {t("common.loading", "Loading…")}
          </Typography>
        ) : isError ? (
          <Typography variant="body2" sx={{ px: 2, py: 1, color: "error.main" }}>
            {t("common.error", "Failed to load libraries.")}
          </Typography>
        ) : filtered.length === 0 ? (
          <Typography variant="body2" sx={{ px: 2, py: 1, color: "text.secondary" }}>
            {t("common.noResults", "No results")}
          </Typography>
        ) : (
          <List
            dense
            disablePadding
            role={resourceKind ? (isMultiSelect ? "group" : "radiogroup") : undefined}
            aria-label="library resources"
          >
            {filtered.map(({ lib, resources: contents }) => {
              const isOpen = !!openMap[lib.id];

              return (
                <Box key={lib.id}>
                  {/* Library row (expand only) */}
                  <ListItem
                    disableGutters
                    secondaryAction={
                      resourceKind && (
                        <IconButton
                          size="small"
                          edge="end"
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleOpen(lib.id);
                          }}
                          aria-label={isOpen ? t("common.collapse", "Collapse") : t("common.expand", "Expand")}
                        >
                          {isOpen ? <KeyboardArrowDownIcon /> : <KeyboardArrowRightIcon />}
                        </IconButton>
                      )
                    }
                  >
                    <ListItemButton onClick={() => toggleOpen(lib.id)}>
                      <ListItemText primary={lib.name} />
                    </ListItemButton>
                  </ListItem>

                  {/* Resources inside the library (single-select) */}
                  {resourceKind && isOpen && contents.length > 0 && (
                    <List disablePadding>
                      {contents.map((r) => {
                        const resChecked = selectedResourceIds.includes(r.id);
                        return (
                          <ListItem key={r.id} dense role={isMultiSelect ? undefined : "radio"} aria-checked={resChecked}>
                            <ListItemButton
                              onClick={() => toggleSelectResource(r.id)}
                              selected={resChecked}
                              sx={{ borderRadius: 1 }}
                            >
                              <ListItemIcon sx={{ minWidth: 36 }}>
                                {isMultiSelect ? (
                                  <Checkbox
                                    edge="start"
                                    tabIndex={-1}
                                    disableRipple
                                    size="small"
                                    checked={resChecked}
                                    onChange={(e) => {
                                      e.stopPropagation();
                                      toggleSelectResource(r.id);
                                    }}
                                  />
                                ) : (
                                  <Radio
                                    edge="start"
                                    tabIndex={-1}
                                    disableRipple
                                    size="small"
                                    checked={resChecked}
                                    onChange={(e) => {
                                      e.stopPropagation();
                                      selectResource(r.id);
                                    }}
                                  />
                                )}
                              </ListItemIcon>
                              <ListItemText primary={r.name} />
                            </ListItemButton>
                          </ListItem>
                        );
                      })}
                    </List>
                  )}
                </Box>
              );
            })}
          </List>
        )}
      </Box>
    </Box>
  );
}
