import React from "react";
import { Box, Stack, Tooltip } from "@mui/material";
import EmptyIcon from "@mui/icons-material/RemoveCircleOutline"; // Icon for empty state
import { Fact } from "../slices/factsStructures";
import { FactBadge } from "./FactBadge"; // Import the new FactBadge component

interface FactMiniaturesProps {
    facts: Fact[];
}

export const FactMiniatures: React.FC<FactMiniaturesProps> = ({ facts }) => {
    return (
        <Box display="flex" justifyContent="center" alignItems="center" width="100%">
            {facts.length > 0 ? (
                <Stack direction="row" spacing={1}>
                    {facts.map((fact, index) => (
                        <FactBadge key={index} fact={fact} />
                    ))}
                </Stack>
            ) : (
                <Tooltip title="No facts available" arrow>
                    <Box display="flex" alignItems="center" justifyContent="center">
                        <EmptyIcon color="disabled" />
                    </Box>
                </Tooltip>
            )}
        </Box>
    );
};
