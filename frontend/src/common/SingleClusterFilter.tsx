import {Grid2, Paper, Skeleton } from "@mui/material";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import 'dayjs/locale/en-gb';
import {ApplicationContext} from "../app/ApplicationContextProvider.tsx";
import {useContext} from "react";
import {ClusterOverview} from "../slices/api.tsx";
import {ClusterScoreCard} from "./ClusterScoreCard.tsx";

dayjs.extend(utc);
dayjs.extend(timezone);

export const SingleClusterFilter = () => {

  const ctx = useContext(ApplicationContext);

  const handleResetSelectedScopes = (c: ClusterOverview) => {
    if(c != null){
      ctx.updateCurrentCluster(c)
    }
  }

  return (
    <Grid2 container>
      <Paper sx={{width: "100%", padding: 2, alignItems: 'center'}}>
        {ctx.allClusters.length > 0 ? (
          <Grid2 container spacing={2} justifyContent='center'>
            {ctx.allClusters.map((scope) => (
              <ClusterScoreCard
                key={scope.alias}
                scope={scope}
                handleUpdateSelectedScopes={handleResetSelectedScopes}
                activate={ctx.currentClusterOverview==scope}>
              </ClusterScoreCard>
            ))}
          </Grid2>
        ):(
          <Skeleton animation="wave" width={"100%"} height={"100%"}/>
        )}
      </Paper>
    </Grid2>
  );
}
