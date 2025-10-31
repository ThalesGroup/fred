import { Avatar, ListItem, ListItemAvatar, ListItemProps, ListItemText, Typography } from "@mui/material";
import { UserSummary } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface UserListElementProps extends ListItemProps {
  user: UserSummary;
}

export function UserListItem({ user, ...listItemProps }: UserListElementProps) {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  const username = `@${user.username}`;

  const avatarChar = fullName
    ? fullName.charAt(0).toUpperCase()
    : user.username
      ? user.username.charAt(0).toUpperCase()
      : "?";

  return (
    <ListItem
      {...listItemProps}
      sx={{
        height: 60,
        borderRadius: 2,
        ...listItemProps.sx,
      }}
      key={listItemProps.key || user.id}
    >
      <ListItemAvatar>
        <Avatar
        //  sx={{ bgcolor: "secondary.main" }}
        >
          {avatarChar}
        </Avatar>
      </ListItemAvatar>
      <ListItemText
        primary={fullName}
        secondary={
          <Typography variant="body2" color="text.secondary">
            {username}
          </Typography>
        }
      />
    </ListItem>
  );
}
