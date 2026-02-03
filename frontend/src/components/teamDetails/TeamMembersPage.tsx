import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  Box,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import { useListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetQuery } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface TeamMembersPageProps {
  teamId: string;
}

export function TeamMembersPage({ teamId }: TeamMembersPageProps) {
  const { t } = useTranslation();

  const { data: members } = useListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetQuery({ teamId: teamId });
  // todo: handle loading
  // todo: handle error
  // todo: handle empty state

  return (
    <Box sx={{ px: 2, pb: 2, display: "flex", height: "100%" }}>
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        {/* Header */}
        <Box sx={{ display: "flex", alignItems: "center", height: "3rem", gap: 0.75, px: 2 }}>
          <Typography variant="body2" color="textSecondary">
            {t("teamMembersPage.headerTitle")}
          </Typography>
          <Tooltip
            title={t("teamMembersPage.headerInfoTooltip")}
            placement="top"
            slotProps={{
              popper: {
                modifiers: [
                  {
                    name: "offset",
                    options: {
                      offset: [0, -12],
                    },
                  },
                ],
              },
            }}
          >
            <InfoOutlinedIcon fontSize="small" color="disabled" />
          </Tooltip>
        </Box>

        {/* Table */}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t("teamMembersPage.tableHeader.username")}</TableCell>
              <TableCell>{t("teamMembersPage.tableHeader.firstName")}</TableCell>
              <TableCell>{t("teamMembersPage.tableHeader.lastName")}</TableCell>
              <TableCell>{t("teamMembersPage.tableHeader.role")}</TableCell>
              <TableCell>{t("teamMembersPage.tableHeader.actions")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {members &&
              members.map((member) => (
                <TableRow key={member.user.id}>
                  <TableCell>{member.user.username}</TableCell>
                  <TableCell>{member.user.first_name}</TableCell>
                  <TableCell>{member.user.last_name}</TableCell>
                  <TableCell>
                    <Select value={member.relation} size="small">
                      <MenuItem value={"owner"}>{t("teamMembersPage.teamRole.owner")}</MenuItem>
                      <MenuItem value={"manager"}>{t("teamMembersPage.teamRole.manager")}</MenuItem>
                      <MenuItem value={"member"}>{t("teamMembersPage.teamRole.member")}</MenuItem>
                    </Select>
                  </TableCell>
                  <TableCell></TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
