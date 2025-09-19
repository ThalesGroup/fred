// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import { useMemo, useState } from "react";
import {
  Box,
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
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { useTranslation } from "react-i18next";
import {
  TagType,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  Resource,
  ResourceKind,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface ResourceLibrariesSelectionCardProps {
  // add "profile" without changing backend enum usage
  libraryType: TagType | "profile"; // "prompt" | "template" | "profile"
  selectedResourceIds: string[];
  setSelectedResourceIds: (ids: string[]) => void;
}

type Lib = Pick<TagWithItemsId, "id" | "name" | "path" | "description">;

export function ChatResourcesSelectionCard({
  libraryType,
  selectedResourceIds,
  setSelectedResourceIds,
}: ResourceLibrariesSelectionCardProps) {
  const { t } = useTranslation();

  // Libraries (as groups to browse)
  const { data: tags = [], isLoading, isError } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: libraryType as TagType,
  });

  // Fetch resources of that kind
  const resourceKind: ResourceKind | undefined = (() => {
    if (libraryType === "prompt") return "prompt" as ResourceKind;
    if (libraryType === "template") return "template" as ResourceKind;
    if (libraryType === "profile") return "profile" as ResourceKind;
    return undefined;
  })();

  // NOTE: this assumes resourceKind is set for supported types
  const { data: fetchedResources = [] } =
    resourceKind
      ? useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: resourceKind })
      : ({ data: [] } as { data: Resource[] });

  const [q, setQ] = useState("");
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
    [tags]
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
    const needle = q.trim().toLowerCase();
    if (!needle) return libs;
    return libs.filter(
      (l) =>
        l.name.toLowerCase().includes(needle) ||
        (l.path ?? "").toLowerCase().includes(needle) ||
        (l.description ?? "").toLowerCase().includes(needle)
    );
  }, [libs, q]);

  // --- single-select helpers ---
  const selectResource = (id: string) => {
    // force single selection
    setSelectedResourceIds([id]);
  };

  const toggleSelectResource = (id: string) => {
    // if already selected → unselect, else select
    const current = selectedResourceIds[0];
    if (current === id) {
      setSelectedResourceIds([]);
    } else {
      setSelectedResourceIds([id]);
    }
  };

  const toggleOpen = (id: string) => setOpenMap((m) => ({ ...m, [id]: !m[id] }));

  const searchLabel = useMemo(() => {
    if (libraryType === "template") return t("chatbot.searchTemplateLibraries", "Search template libraries");
    if (libraryType === "profile") return t("chatbot.searchProfileLibraries", "Search profile libraries");
    return t("chatbot.searchPromptLibraries", "Search prompt libraries");
  }, [libraryType, t]);

  return (
    <Box sx={{ width: 420, height: 460, display: "flex", flexDirection: "column" }}>
      {/* Search libraries */}
      <Box sx={{ mx: 2, mt: 2, mb: 1 }}>
        <TextField
          autoFocus
          size="small"
          fullWidth
          label={searchLabel}
          value={q}
          onChange={(e) => setQ(e.target.value)}
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
          <List dense disablePadding role="radiogroup" aria-label="library resources">
            {filtered.map((lib) => {
              const contents = resourcesByTag.get(lib.id) ?? [];
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
                        const resChecked = selectedResourceIds[0] === r.id;
                        return (
                          <ListItem key={r.id} dense role="radio" aria-checked={resChecked}>
                            <ListItemButton
                              onClick={() => toggleSelectResource(r.id)}
                              selected={resChecked}
                              sx={{ borderRadius: 1 }}
                            >
                              <ListItemIcon sx={{ minWidth: 36 }}>
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
