import { useMemo, useState } from "react";
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
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";

export type PluginItem = {
  id: string;
  name: string;
  group?: string;         // pour regrouper (ex: catégorie)
  description?: string;
};

export function PluginSelector({
  items,
  selectedIds,
  onChange,
  title = "Plugins",
  searchPlaceholder = "Search plugins…",
}: {
  items: PluginItem[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  title?: string;
  searchPlaceholder?: string;
}) {
  // group by "group"
  const groups = useMemo(() => {
    const map = new Map<string, PluginItem[]>();
    for (const it of items) {
      const g = it.group || "General";
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(it);
    }
    // sort groups and items by name
    for (const [k, arr] of map) arr.sort((a, b) => a.name.localeCompare(b.name));
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [items]);

  const [q, setQ] = useState("");
  const [openMap, setOpenMap] = useState<Record<string, boolean>>({});

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return groups;
    return groups
      .map(([g, arr]) => [
        g,
        arr.filter(
          (it) =>
            it.name.toLowerCase().includes(needle) ||
            (it.description ?? "").toLowerCase().includes(needle)
        ),
      ])
      .filter(([_, arr]) => (arr as PluginItem[]).length > 0) as [string, PluginItem[]][];
  }, [groups, q]);

  const toggle = (id: string) => {
    const set = new Set(selectedIds);
    set.has(id) ? set.delete(id) : set.add(id);
    onChange(Array.from(set));
  };

  const toggleOpen = (g: string) =>
    setOpenMap((m) => ({ ...m, [g]: !m[g] }));

  return (
    <Box sx={{ width: 420, height: 460, display: "flex", flexDirection: "column" }}>
      <Box sx={{ px: 2, pt: 2, pb: 1 }}>
        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
          {title}
        </Typography>
        <TextField
          autoFocus
          size="small"
          fullWidth
          placeholder={searchPlaceholder}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", overflowX: "hidden", px: 1, pb: 1.5 }}>
        <List dense disablePadding>
          {filtered.map(([groupName, groupItems]) => {
            const isOpen = !!openMap[groupName];
            return (
              <Box key={groupName}>
                <ListItem
                  disableGutters
                  secondaryAction={
                    <IconButton
                      size="small"
                      edge="end"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleOpen(groupName);
                      }}
                    >
                      {isOpen ? <KeyboardArrowDownIcon /> : <KeyboardArrowRightIcon />}
                    </IconButton>
                  }
                >
                  <ListItemButton onClick={() => toggleOpen(groupName)}>
                    <ListItemText primary={groupName} />
                  </ListItemButton>
                </ListItem>

                {isOpen && (
                  <List disablePadding>
                    {groupItems.map((it) => {
                      const checked = selectedIds.includes(it.id);
                      return (
                        <ListItem key={it.id} dense>
                          <ListItemButton selected={checked} onClick={() => toggle(it.id)}>
                            <ListItemIcon sx={{ minWidth: 36 }}>
                              <Checkbox
                                edge="start"
                                tabIndex={-1}
                                disableRipple
                                checked={checked}
                                onChange={() => toggle(it.id)}
                              />
                            </ListItemIcon>
                            <ListItemText
                              primary={it.name}
                              secondary={it.description}
                              secondaryTypographyProps={{ noWrap: true }}
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
      </Box>
    </Box>
  );
}
