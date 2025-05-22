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

import { Box, Grid2, Theme, useMediaQuery, useTheme } from "@mui/material";
import { ResourceScoreSimpleRadarChart } from "./ResourceScoreSimpleRadarChart.tsx";
import { WorkloadScores } from "../slices/scoresStructures.tsx";

interface ResourceIdentityCardProps {
    name: string;
    score: WorkloadScores;
}
const mapScoresToAttributes = (scores: WorkloadScores) => {
    return Object.keys(scores).map((key) => ({
        attribut_name: key,
        value: scores[key].score * 10  // Scale score for radar chart (optional)
    }));
};

export const ResourceScoreCard = ({
    name,
    score,
}: ResourceIdentityCardProps) => {
    const theme = useTheme<Theme>();
    const isSmallScreen = useMediaQuery(theme.breakpoints.down("sm")); // Detect if screen is small
    const radarChartData = mapScoresToAttributes(score);
    return (
        <Box
            sx={{
                display: "flex",
                flexDirection: "row",
                alignItems: "center",
                justifyContent: "space-between",
                height: "100%",  // Ensure it takes full height
                width: "100%",   // Full width
            }}
        >
            {!isSmallScreen && (
                <Grid2 
                    size={{ xs: 12 }} 
                    sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}
                >
                    <Box sx={{ width: "100%", height: "100%" }}>
                        <ResourceScoreSimpleRadarChart
                            zoom={"50%"}
                            application_name={name}
                            data={radarChartData}
                            unit={"/100"}
                        />
                    </Box>
                </Grid2>
            )}
        </Box>
    );
};
