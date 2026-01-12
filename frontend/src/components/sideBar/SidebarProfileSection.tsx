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

  // Find the highest priority role without sorting the entire array
  const getPrimaryRole = (): string | undefined => {
    if (roles.length === 0) return undefined;

    const order = ["admin", "editor", "viewer"];
    let primaryRole = roles[0];
    let primaryIndex = order.indexOf(primaryRole);

    for (const role of roles) {
      const index = order.indexOf(role);
      if (index !== -1 && (primaryIndex === -1 || index < primaryIndex)) {
        primaryRole = role;
        primaryIndex = index;
      }
    }

    return primaryRole;
  };

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
      <ListItemText primary={KeyCloakService.GetUserFullName()} secondary={getPrimaryRole()} />
    </ListItem>
  );
}
