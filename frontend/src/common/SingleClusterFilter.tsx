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

import { Grid2, Paper, Skeleton } from "@mui/material";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";
import "dayjs/locale/en-gb";
import { K8ApplicationContext } from "../app/K8ApplicationContextProvider.tsx";
import { useContext } from "react";
import { ClusterOverview } from "../frugalit/slices/api.tsx";
import { ClusterScoreCard } from "./ClusterScoreCard.tsx";

dayjs.extend(utc);
dayjs.extend(timezone);

export const SingleClusterFilter = () => {
  const ctx = useContext(K8ApplicationContext);

  const handleResetSelectedScopes = (c: ClusterOverview) => {
    if (c != null) {
      ctx.updateCurrentCluster(c);
    }
  };

  return (
    <Grid2 container>
      <Paper sx={{ width: "100%", padding: 2, alignItems: "center" }}>
        {ctx.allClusters.length > 0 ? (
          <Grid2 container spacing={2} justifyContent="center">
            {ctx.allClusters.map((scope) => (
              <ClusterScoreCard
                key={scope.alias}
                scope={scope}
                handleUpdateSelectedScopes={handleResetSelectedScopes}
                activate={ctx.currentClusterOverview == scope}
              ></ClusterScoreCard>
            ))}
          </Grid2>
        ) : (
          <Skeleton animation="wave" width={"100%"} height={"100%"} />
        )}
      </Paper>
    </Grid2>
  );
};
