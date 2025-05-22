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
import { Grid2, Typography } from "@mui/material";
import { WorkloadScores, ScoreAttribute } from "../slices/scoresStructures";



// Helper function to compute the overall score
const computeOverallScore = (scores: WorkloadScores): number => {
    const total = Object.values(scores).reduce((sum, attr: ScoreAttribute) => sum + attr.score, 0); // Scale the score
    return total / Object.keys(scores).length;
};

// Helper functions to determine the score type
const isA = (score: number): boolean => score >= 8;
const isB = (score: number): boolean => score >= 6 && score < 8;
const isC = (score: number): boolean => score >= 4 && score < 6;
const isD = (score: number): boolean => score >= 2 && score < 4;

// Helper function to determine the letter and color for a score
const getScoreDetails = (score: number) => {
    if (isA(score)) return { letter: "A", color: "green" };
    if (isB(score)) return { letter: "B", color: "#9ACD32" };
    if (isC(score)) return { letter: "C", color: "#dbc60b" };
    if (isD(score)) return { letter: "D", color: "orange" };
    return { letter: "E", color: "red" };
};

interface ScoreLetterProps {
    score?: number; // For single score display
}
export const ScoreLetter: React.FC<ScoreLetterProps> = ({ score }) => {
    if (score === undefined) {
        throw new Error("For 'simple' mode, the 'score' prop is required.");
    }
    const { letter, color } = getScoreDetails(score);
    return (
        <Grid2
            container
            display="flex"
            justifyContent="center"
            alignItems="center"
            sx={{
                backgroundColor: color,
                borderRadius: 1,
                width: "25px",
                height: "25px",
            }}
        >
            <Typography variant="body2" color="white" sx={{ fontWeight: 900 }}>
                {letter}
            </Typography>
        </Grid2>
    );
}

interface WorkloadEcoScoreProps {
    workload_scores?: WorkloadScores; // For complex score display
}
export const WorkloadEcoScore: React.FC<WorkloadEcoScoreProps> = ({ workload_scores }) => {
    const overallScore = computeOverallScore(workload_scores);
    return (
        <Grid2 container justifyContent="center" sx={{  padding: 0 }}>
            <Grid2 container spacing={0} p={1} flexDirection="column" sx={{ border: "solid grey", borderRadius: 2 }}>
                <Grid2 container flexWrap="nowrap" spacing={0} justifyContent="center" alignItems="center">
                    {["A", "B", "C", "D", "E"].map((letter, index) => {
                        const color = ["green", "#9ACD32", "#dbc60b", "orange", "red"][index];
                        const isHighlighted = getScoreDetails(overallScore).letter === letter;
                        return (
                            <Grid2
                                key={letter}
                                container
                                display="flex"
                                justifyContent="center"
                                alignItems="center"
                                sx={{
                                    backgroundColor: color,
                                    borderRadius: isHighlighted ? 1 : undefined,
                                    width: isHighlighted ? "28px" : "20px",
                                    height: isHighlighted ? "28px" : "20px",
                                }}
                            >
                                <Typography
                                    variant="body2"
                                    color="white"
                                    sx={{ opacity: isHighlighted ? 1 : 0.8, fontWeight: isHighlighted ? 900 : 100 }}
                                >
                                    {letter}
                                </Typography>
                            </Grid2>
                        );
                    })}
                </Grid2>
            </Grid2>
        </Grid2>
    );
};
