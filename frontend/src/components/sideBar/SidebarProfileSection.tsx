import SettingsIcon from "@mui/icons-material/Settings";
import { IconButton, ListItem, ListItemIcon, ListItemText } from "@mui/material";
import { Link } from "react-router-dom";
import { KeyCloakService } from "../../security/KeycloakService";
import { UserAvatar } from "../profile/UserAvatar";

interface SidebarProfileSectionProps {
  isSidebarOpen: boolean;
}

export function SidebarProfileSection({ isSidebarOpen }: SidebarProfileSectionProps) {
  const roles = KeyCloakService.GetUserRoles();

  return (
    <ListItem
      dense
      sx={{ py: 1 }}
      secondaryAction={
        <IconButton component={Link} to="/settings">
          <SettingsIcon />
        </IconButton>
      }
    >
      <ListItemIcon>{isSidebarOpen && <UserAvatar />}</ListItemIcon>
      <ListItemText primary={KeyCloakService.GetUserFullName()} secondary={roles.length > 0 ? roles[0] : undefined} />
    </ListItem>
  );
}
