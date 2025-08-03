import {
  Box,
  Checkbox,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Tooltip,
  Typography,
} from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Prompt } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface PromptRowAction {
  icon: React.ReactNode;
  name: string;
  handler: (prompt: Prompt) => void;
}

interface PromptTableProps {
  prompts: Prompt[];
  onEditPrompt?: (prompt: Prompt) => void;
  onDeletePrompt?: (prompt: Prompt) => void;
  actions?: PromptRowAction[];
  showSelection?: boolean;
}

export const PromptTable: React.FC<PromptTableProps> = ({
  prompts,
  onEditPrompt,
  onDeletePrompt,
  actions = [],
  showSelection = false,
}) => {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<keyof Prompt>("name");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  const sortedPrompts = useMemo(() => {
    const sorted = [...prompts].sort((a, b) => {
      const aVal = a[sortBy] ?? "";
      const bVal = b[sortBy] ?? "";
      return sortDirection === "asc"
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    });
    return sorted;
  }, [prompts, sortBy, sortDirection]);

  const toggleSelection = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  };

  return (
    <TableContainer>
      <Table>
        <TableHead>
          <TableRow>
            {showSelection && (
              <TableCell padding="checkbox">
                <Checkbox
                  checked={selected.length === prompts.length}
                  onChange={(e) =>
                    setSelected(e.target.checked ? prompts.map((p) => p.id) : [])
                  }
                />
              </TableCell>
            )}
            <TableCell>
              <TableSortLabel
                active={sortBy === "name"}
                direction={sortBy === "name" ? sortDirection : "asc"}
                onClick={() => {
                  setSortBy("name");
                  setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
                }}
              >
                {t("promptTable.name")}
              </TableSortLabel>
            </TableCell>
            <TableCell>{t("promptTable.content")}</TableCell>
            <TableCell align="right">{t("promptTable.actions")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sortedPrompts.map((prompt) => (
            <TableRow key={prompt.id} hover>
              {showSelection && (
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={selected.includes(prompt.id)}
                    onChange={() => toggleSelection(prompt.id)}
                  />
                </TableCell>
              )}
              <TableCell>
                <Typography variant="body2" fontWeight={500}>
                  {prompt.name}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" noWrap maxWidth={500}>
                  {prompt.content}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Box display="flex" gap={1} justifyContent="flex-end">
                  {onEditPrompt && (
                    <Tooltip title={t("promptTable.edit")}>
                      <IconButton size="small" onClick={() => onEditPrompt(prompt)}>
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                  )}
                  {onDeletePrompt && (
                    <Tooltip title={t("promptTable.delete")}>
                      <IconButton size="small" onClick={() => onDeletePrompt(prompt)}>
                        <DeleteIcon />
                      </IconButton>
                    </Tooltip>
                  )}
                  {actions.map((action, idx) => (
                    <Tooltip title={action.name} key={idx}>
                      <IconButton size="small" onClick={() => action.handler(prompt)}>
                        {action.icon}
                      </IconButton>
                    </Tooltip>
                  ))}
                </Box>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};
