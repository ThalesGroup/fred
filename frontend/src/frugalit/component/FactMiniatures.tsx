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
