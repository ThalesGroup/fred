import { Box, Button, MenuItem, Stack, TextField, Typography, Alert } from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useListGroupsKnowledgeFlowV1GroupsGetQuery,
  useListUsersKnowledgeFlowV1UsersGetQuery,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { KeyCloakService } from "../security/KeycloakService";

type RelationOption = "owner" | "manager" | "member";

export function AdminGroupRolesPage() {
  const { t } = useTranslation();
  const { data: groups = [] } = useListGroupsKnowledgeFlowV1GroupsGetQuery({
    limit: 10000,
    offset: 0,
    memberOnly: false,
  });
  const { data: users = [] } = useListUsersKnowledgeFlowV1UsersGetQuery();

  const [groupId, setGroupId] = useState<string>("");
  const [userId, setUserId] = useState<string>("");
  const [relation, setRelation] = useState<RelationOption>("member");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string>("");

  const sortedGroups = useMemo(() => [...groups].sort((a, b) => a.name.localeCompare(b.name)), [groups]);
  const sortedUsers = useMemo(() => [...users].sort((a, b) => (a.username || "").localeCompare(b.username || "")), [users]);

  const canSubmit = groupId && userId && relation;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setStatus("loading");
    setError("");
    try {
      const token = KeyCloakService.GetToken ? KeyCloakService.GetToken() : localStorage.getItem("keycloak_token") || "";
      const res = await fetch(`/knowledge-flow/v1/groups/${groupId}/relations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          target_id: userId,
          target_type: "user",
          relation,
        }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || `HTTP ${res.status}`);
      }
      setStatus("success");
    } catch (e: any) {
      setStatus("error");
      setError(e?.message || "Unknown error");
    }
  };

  return (
    <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 2, maxWidth: 520 }}>
      <Typography variant="h6">{t("admin.groupRoles.title", "Assigner un rôle à un utilisateur")}</Typography>
      <Stack spacing={2}>
        <TextField
          select
          label={t("admin.groupRoles.group", "Groupe")}
          value={groupId}
          onChange={(e) => setGroupId(e.target.value)}
          size="small"
        >
          {sortedGroups.map((g) => (
            <MenuItem key={g.id} value={g.id}>
              {g.name}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          label={t("admin.groupRoles.user", "Utilisateur")}
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          size="small"
        >
          {sortedUsers.map((u) => (
            <MenuItem key={u.id} value={u.id}>
              {u.username || u.id}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          label={t("admin.groupRoles.relation", "Rôle")}
          value={relation}
          onChange={(e) => setRelation(e.target.value as RelationOption)}
          size="small"
        >
          <MenuItem value="owner">owner</MenuItem>
          <MenuItem value="manager">manager</MenuItem>
          <MenuItem value="member">member</MenuItem>
        </TextField>

        <Button variant="contained" onClick={handleSubmit} disabled={!canSubmit || status === "loading"}>
          {t("admin.groupRoles.assign", "Assigner")}
        </Button>

        {status === "success" && (
          <Alert severity="success">{t("admin.groupRoles.success", "Rôle ajouté avec succès")}</Alert>
        )}
        {status === "error" && <Alert severity="error">{error || t("common.error")}</Alert>}
      </Stack>
    </Box>
  );
}
