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
import { UserSummary } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

// todo: get type from codegen from backend
interface TeamMember extends UserSummary {
  role: "owner" | "manager" | "member";
}

const members: TeamMember[] = [
  { id: "1", username: "asmith", first_name: "Alice", last_name: "Smith", role: "owner" },
  { id: "2", username: "bjohnson", first_name: "Bob", last_name: "Johnson", role: "manager" },
  { id: "3", username: "cwhite", first_name: "Carol", last_name: "White", role: "manager" },
  { id: "4", username: "dbrown", first_name: "David", last_name: "Brown", role: "member" },
  { id: "5", username: "edavis", first_name: "Emma", last_name: "Davis", role: "member" },
  { id: "6", username: "fmiller", first_name: "Frank", last_name: "Miller", role: "member" },
  { id: "7", username: "gwilson", first_name: "Grace", last_name: "Wilson", role: "member" },
  { id: "8", username: "hmoore", first_name: "Henry", last_name: "Moore", role: "member" },
  { id: "9", username: "itaylor", first_name: "Iris", last_name: "Taylor", role: "member" },
  { id: "10", username: "janderson", first_name: "Jack", last_name: "Anderson", role: "member" },
  { id: "11", username: "kthomas", first_name: "Kate", last_name: "Thomas", role: "member" },
  { id: "12", username: "ljackson", first_name: "Leo", last_name: "Jackson", role: "member" },
  { id: "13", username: "mmartin", first_name: "Mary", last_name: "Martin", role: "member" },
  { id: "14", username: "nlee", first_name: "Nathan", last_name: "Lee", role: "member" },
  { id: "15", username: "oharris", first_name: "Olivia", last_name: "Harris", role: "member" },
  { id: "16", username: "pclark", first_name: "Peter", last_name: "Clark", role: "member" },
  { id: "17", username: "qlewis", first_name: "Quinn", last_name: "Lewis", role: "member" },
  { id: "18", username: "rrobinson", first_name: "Rachel", last_name: "Robinson", role: "member" },
  { id: "19", username: "swalker", first_name: "Steve", last_name: "Walker", role: "member" },
  { id: "20", username: "thall", first_name: "Tina", last_name: "Hall", role: "member" },
  { id: "21", username: "uallen", first_name: "Uma", last_name: "Allen", role: "member" },
  { id: "22", username: "vyoung", first_name: "Victor", last_name: "Young", role: "member" },
  { id: "23", username: "wking", first_name: "Wendy", last_name: "King", role: "member" },
  { id: "24", username: "xwright", first_name: "Xavier", last_name: "Wright", role: "member" },
  { id: "25", username: "ylopez", first_name: "Yara", last_name: "Lopez", role: "member" },
];

export function TeamMembersPage() {
  const { t } = useTranslation();

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
            {members.map((member) => (
              <TableRow key={member.id}>
                <TableCell>{member.username}</TableCell>
                <TableCell>{member.first_name}</TableCell>
                <TableCell>{member.last_name}</TableCell>
                <TableCell>
                  <Select value={member.role} size="small">
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
