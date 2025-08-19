// components/chat/ResourceLibrariesSelectionCard.tsx
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
  useListResourcesKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface ResourceLibrariesSelectionCardProps {
  libraryType: TagType; // "prompt" | "template"
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
  const { data: tags = [], isLoading, isError } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: libraryType });

  // Fetch resources of that kind
  const resourceKind: ResourceKind | undefined =
    libraryType === "prompt" ? "prompt" : libraryType === "template" ? "template" : undefined;

  const { data: fetchedResources = [] } =
    resourceKind
      ? useListResourcesKnowledgeFlowV1ResourcesGetQuery({
          kind: resourceKind,
          tags: undefined,
        })
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

  const toggleSelectResource = (id: string) => {
    const sel = new Set(selectedResourceIds);
    sel.has(id) ? sel.delete(id) : sel.add(id);
    setSelectedResourceIds(Array.from(sel));
  };

  const toggleOpen = (id: string) => setOpenMap((m) => ({ ...m, [id]: !m[id] }));

  return (
    <Box sx={{ width: 420, height: 460, display: "flex", flexDirection: "column" }}>
      {/* Search libraries */}
      <Box sx={{ mx: 2, mt: 2, mb: 1 }}>
        <TextField
          autoFocus
          size="small"
          fullWidth
          label={
            libraryType === "template"
              ? t("chatbot.searchTemplateLibraries", "Search template libraries")
              : t("chatbot.searchPromptLibraries", "Search prompt libraries")
          }
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
          <List dense disablePadding>
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
                      <ListItemText
                        primary={lib.name}
                        />
                    </ListItemButton>
                  </ListItem>

                  {/* Resources inside the library (selectable) */}
                  {resourceKind && isOpen && contents.length > 0 && (
                    <List disablePadding>
                      {contents.map((r) => {
                        const resChecked = selectedResourceIds.includes(r.id);
                        return (
                          <ListItem key={r.id} dense >
                            <ListItemButton onClick={() => toggleSelectResource(r.id)} selected={resChecked}>
                              <ListItemIcon sx={{ minWidth: 36 }}>
                                <Checkbox
                                  edge="start"
                                  tabIndex={-1}
                                  disableRipple
                                  checked={resChecked}
                                  onChange={() => toggleSelectResource(r.id)}
                                />
                              </ListItemIcon>
                              <ListItemText
                                primary={r.name}
                              />
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
