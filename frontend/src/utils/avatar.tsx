// utils/getUserAvatar.tsx
import { Avatar, Badge, Box, Typography, useTheme } from "@mui/material";
import { red, blue, green, purple, orange, teal, yellow } from "@mui/material/colors";
import { Fact } from "../slices/factsStructures";
import AppsIcon from '@mui/icons-material/Apps';
import AssignmentIcon from '@mui/icons-material/Assignment';
import AttachMoneyIcon from '@mui/icons-material/AttachMoney';
import VerifiedIcon from '@mui/icons-material/Verified';
import SecurityIcon from '@mui/icons-material/Security';
import StarIcon from "@mui/icons-material/Star";
const colors = [red[800], blue[800], green[800], purple[800], orange[800]];
export function getFactTypeIcon(factType: string, size: number = 12) {
    const theme = useTheme();
    const color = theme.palette.mode === "dark" 
        ? theme.palette.primary.contrastText 
        : theme.palette.text.primary;
    switch (factType) {
        case 'domain':
            return <AppsIcon fontSize="small" 
            sx={{ fontSize: size, color: color }} />;
        case 'requirement':
            return <AssignmentIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
        case 'cost':
            return <AttachMoneyIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
        case 'compliance':
            return <VerifiedIcon fontSize="small" sx={{ fontSize: size, color: color }} />;
        case 'security':
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
    return (
        <Avatar sx={{ bgcolor: avatarColor, width: size, height: size }}>
            {userName[0].toUpperCase()}
        </Avatar>
    );
};


export const getFactAvatar = (fact: Fact,  size: number = 20) => {

    const theme = useTheme(); // Access the theme object

    // Define fact type colors based on theme.palette
    const factTypeColors: Record<string, string> = {
        domain: theme.palette.info.dark,          // Replace with your theme colors
        requirement: theme.palette.success.main,  // Success color for requirements
        cost: theme.palette.warning.main,         // Warning color for cost
        compliance: theme.palette.primary.main,   // Primary color for compliance
        security: theme.palette.error.main,       // Error color for security
    };
    const factFallbackColor = theme.palette.grey[500]; // Fallback color


     // Determine color based on the user's name
     const avatarColor = factTypeColors[fact.type] || factFallbackColor;
    // Return an Avatar component with the initial and dynamic color
    return (
        <Box
            sx={{
                border: `3px solid ${avatarColor}`, // Colored border
                
                backgroundColor: theme.palette.common.white, 
                color: theme.palette.primary.contrastText, // Text color for contrast
                width: size * 3, // Adjust width dynamically
                height: size * 1.2, // Adjust height dynamically
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "12px", // Rounded corners
                paddingX: 2, // Horizontal padding for content
                textAlign: "center",
                overflow: "hidden", // Prevent text overflow
                whiteSpace: "nowrap", // Prevent wrapping
                textOverflow: "ellipsis", // Add ellipsis if title is too long
                fontWeight: "bold",
                fontSize: size * 0.6, // Font size relative to size
            }}
        >
            <Typography variant="body2" noWrap sx={{
                color: theme.palette.common.black,
            }}>
                {fact.title}
            </Typography>
        </Box>
    );
};

const expertColors: Record<string, string> = {
    "Fred": teal[500],
};
const fallbackColor = green[500];

export const getAgentAvatar = (name: string,  size: number = 28) => {
    const color = expertColors[name] || fallbackColor; // Use mapped color or fallback
   return (
       <Avatar sx={{ bgcolor: color, width: size, height: size }}>
           {name?.toUpperCase().charAt(0)}
       </Avatar>
   );
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
            <Avatar sx={{ bgcolor: color, width: size, height: size }}>
                {name?.toUpperCase().charAt(0)}
            </Avatar>
        </Badge>
    );
};


