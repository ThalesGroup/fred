import { Avatar, ListItem, ListItemAvatar, ListItemProps, ListItemText, Typography } from "@mui/material";
import { GroupSummary } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface GroupListElementProps extends ListItemProps {
  group: GroupSummary;
}

export function GroupListItem({ group, ...listItemProps }: GroupListElementProps) {
  return (
    <ListItem
      {...listItemProps}
      sx={{
        height: 60,
        borderRadius: 2,
        ...listItemProps.sx,
      }}
      key={listItemProps.key || group.id}
    >
      <ListItemAvatar>
        <Avatar
          sx={{
            // bgcolor: "secondary.main"
            borderRadius: 2,
          }}
          variant="square"
        >
          {group.name.charAt(0).toUpperCase()}
        </Avatar>
      </ListItemAvatar>
      <ListItemText
        primary={group.name}
        secondary={
          <Typography variant="body2" color="text.secondary">
            {group.total_member_count} members
          </Typography>
        }
      />
    </ListItem>
  );
}
