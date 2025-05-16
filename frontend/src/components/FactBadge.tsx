import React from "react";
import { Badge, Divider, Tooltip, Typography } from "@mui/material";
import { getFactAvatar, getFactTypeIcon } from "../utils/avatar";
import { Fact } from "../slices/factsStructures";

interface FactBadgeProps {
    fact: Fact;
    size?: number; // Allow customization of badge size
}

export const FactBadge: React.FC<FactBadgeProps> = ({ fact, size = 36 }) => {
    return (
        <Tooltip enterDelay={1000}
            title={
                <>
                    <Typography variant="h5" color="primary.contrastText">
                        {fact.title}
                    </Typography>
                    <Typography variant="h6" color="primary.contrastText" gutterBottom>
                        type:{fact.type}
                    </Typography>
                    <Typography variant="subtitle2" color="primary.contrastText" gutterBottom>
                        {new Date(fact.date).toLocaleDateString('en-US', {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                        })}{" "}
                        by {fact.user}
                    </Typography>
                    <Divider sx={{ borderColor: "primary.contrastText", my: 2 }} />
                    <Typography variant="body1" color="primary.contrastText" sx={{ fontStyle: "italic" }}>
                        &quot;{fact.content}&quot;
                    </Typography>
                </>
            }
            arrow={false}
        >
            <Badge
                overlap="circular"
                anchorOrigin={{ vertical: "top", horizontal: "right" }}
                badgeContent={
                    fact.type ? getFactTypeIcon(fact.type, size / 2) : null
                }
                sx={{
                    "& .MuiBadge-badge": {
                        backgroundColor: "background.paper",
                        borderRadius: "50%",
                        minWidth: size / 1.4, // Control the overall width of the badge
                        minHeight: size / 1.4, // Control the overall height of the badge
                        padding: "2px",
                        boxShadow: 0, // Adds a subtle shadow to the badge
                        transform: "translate(100%, -60%)",
                        border: "1px solid", 
                    },
                }}
            >
                {getFactAvatar(fact, size)}
            </Badge>
        </Tooltip>
    );
};
