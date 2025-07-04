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

import { useParams, useLocation } from "react-router-dom";
import { Typography } from "@mui/material";
import { ResourceScoreDetailRadarChart } from "../frugalit/component/ResourceScoreDetailRadarChart";
import { WorkloadScores } from "../frugalit/slices/scoresStructures";

const mapScoresToAttributes = (scores: WorkloadScores) => {
  return Object.entries(scores).map(([key, { score, reason }]) => ({
    attribut_name: key,
    display_text: `${key.toUpperCase()}`, // Include reason with the attribute name
    value: score * 10, // Scale score for radar chart (optional)
    reason: reason,
  }));
};
export const Scores = () => {
  const { cluster, namespace, application } = useParams(); // Get URL params
  const location = useLocation();
  const score = location.state?.score as WorkloadScores | undefined; // Get score from location.state if passed

  // TODO: Fetch or handle score data if it's not passed through state
  if (!score) {
    console.log(" state not defined", cluster, namespace, application);
    return <Typography variant="body2">Score data not available. Please navigate through the main view.</Typography>;
  }

  return (
    <ResourceScoreDetailRadarChart
      zoom={"50%"}
      application_name={application}
      data={mapScoresToAttributes(score)}
      unit={"/100"}
    />
  );
};
