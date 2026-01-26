import GroupsIcon from "@mui/icons-material/Groups";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import { Avatar, AvatarGroup, Box, Paper, styled, Tooltip, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { GroupSummary } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { getInitials } from "../../utils/getInitials";
import InvisibleLink from "../InvisibleLink";

const HoverBox = styled(Box)<{ userIsMember: boolean }>(({ theme, userIsMember }) => {
  if (!userIsMember) {
    return {};
  }

  return {
    "&:hover": {
      backgroundColor: theme.palette.action.hover,
    },
  };
});

export interface TeamCardProps {
  team: GroupSummary;
  userIsMember?: boolean;
}

export function TeamCard({ team, userIsMember = false }: TeamCardProps) {
  const { t } = useTranslation();

  // Offset a tooltp down from 12px
  const tooltipOffset = {
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
  };

  const cardContent = (
    <Paper elevation={2} sx={{ borderRadius: 2, userSelect: "none" }}>
      <HoverBox
        userIsMember={userIsMember}
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
          borderRadius: 2,
          overflow: "hidden",
          height: "100%",
        }}
      >
        {/* Banner */}
        <img
          src={team.banner_image_url}
          alt={`${team.name} avatar`}
          style={{ objectFit: "cover", backgroundRepeat: "no-repeat", height: "6rem" }}
        />

        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "stretch",
            px: 2,
            pt: 1.5,
            pb: 2,
            gap: 1.5,
            flexGrow: 1,
          }}
        >
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "stretch" }}>
            {/* Title */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography
                variant="h6"
                sx={{ flexGrow: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {team.name}
              </Typography>
              {team.is_private && (
                <Tooltip title={t("teamCard.privateTeamTooltip")} placement="top" slotProps={tooltipOffset}>
                  <LockOutlinedIcon />
                </Tooltip>
              )}
            </Box>

            {/* Member count */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <GroupsIcon fontSize="small" />
              <Typography variant="body2">
                {team.member_count} {t("teamCard.memberCountLabel")}
              </Typography>
            </Box>
          </Box>

          {/* Description */}
          <Box
            sx={{
              flexGrow: 1,
              lineClamp: 3,
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 3,
            }}
          >
            <Typography variant="body2" color="textSecondary">
              {team.description}
            </Typography>
          </Box>

          {/* List of owners */}
          <Box sx={{ display: "flex" }}>
            <AvatarGroup max={4}>
              {team.owners.map((owner) => (
                <Tooltip
                  title={`${owner.first_name} ${owner.last_name}`}
                  key={owner.id}
                  placement="top"
                  slotProps={tooltipOffset}
                >
                  <Avatar
                    sizes="small"
                    sx={{ width: 24, height: 24, fontSize: "0.75rem" }}
                    // Set border to the same color as the Paper
                    style={{ borderColor: "#232323" }}
                  >
                    {getInitials(owner.username)}
                  </Avatar>
                </Tooltip>
              ))}
            </AvatarGroup>
          </Box>
        </Box>
      </HoverBox>
    </Paper>
  );

  return userIsMember ? <InvisibleLink to={`/team/${team.id}`}>{cardContent}</InvisibleLink> : cardContent;
}
