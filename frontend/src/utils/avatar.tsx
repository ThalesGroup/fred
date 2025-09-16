// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// utils/getUserAvatar.tsx
import { Avatar, Badge, useTheme } from "@mui/material";
import { red, blue, green, purple, orange, teal, yellow } from "@mui/material/colors";
import AppsIcon from "@mui/icons-material/Apps";
import AssignmentIcon from "@mui/icons-material/Assignment";
import AttachMoneyIcon from "@mui/icons-material/AttachMoney";
import VerifiedIcon from "@mui/icons-material/Verified";
import SecurityIcon from "@mui/icons-material/Security";
import StarIcon from "@mui/icons-material/Star";
const colors = [red[800], blue[800], green[800], purple[800], orange[800]];
export function getFactTypeIcon(factType: string, size: number = 12) {
  const theme = useTheme();
  const color = theme.palette.mode === "dark" ? theme.palette.primary.contrastText : theme.palette.text.primary;
  switch (factType) {
    case "domain":
      return <AppsIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
    case "requirement":
      return <AssignmentIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
    case "cost":
      return <AttachMoneyIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
    case "compliance":
      return <VerifiedIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
    case "security":
      return <SecurityIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
    default:
      return null; // No icon for unknown types
  }
}
/**
 * Generates a user avatar component with a dynamic background color based on the user's name.
 *
 * @param {string} userName - The name of the user for which the avatar is generated.
 * @param {number} [size=40] - The size of the avatar. Defaults to 40 if not provided.
 * @returns {JSX.Element} An Avatar component with the user's initial and a background color.
 */
export const getUserAvatar = (userName: string, size: number = 40) => {
  // Determine color based on the user's name
  const colorIndex = userName.charCodeAt(0) % colors.length;
  const avatarColor = colors[colorIndex];

  // Return an Avatar component with the initial and dynamic color
  return <Avatar sx={{ bgcolor: avatarColor, width: size, height: size }}>{userName[0].toUpperCase()}</Avatar>;
};

const expertColors: Record<string, string> = {
  Fred: teal[500],
};
const fallbackColor = green[500];

export const getAgentAvatar = (name: string, size: number = 28) => {
  const color = expertColors[name] || fallbackColor; // Use mapped color or fallback
  return <Avatar sx={{ bgcolor: color, width: size, height: size }}>{name?.toUpperCase().charAt(0)}</Avatar>;
};
export const getAgentBadge = (name: string, size: number = 28) => {
  const color = expertColors[name] || fallbackColor; // Use mapped color or fallback

  return (
    <Badge
      overlap="circular"
      badgeContent={
        name === "Fred" ? (
          <StarIcon
            sx={{
              color: yellow[800], // Star color
              fontSize: size / 2, // Adjust size of the star
            }}
          />
        ) : null
      }
      anchorOrigin={{ vertical: "top", horizontal: "right" }} // Position of the star
    >
      <Avatar sx={{ bgcolor: color, width: size, height: size }}>{name?.toUpperCase().charAt(0)}</Avatar>
    </Badge>
  );
};
