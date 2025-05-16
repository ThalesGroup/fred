import { PageBodyWrapper } from "../common/PageBodyWrapper.tsx";
import 'dayjs/locale/en-gb';
import { ApplicationContext } from '../app/ApplicationContextProvider.tsx';
import { useContext, useEffect, useState } from "react";
import { useSearchParams } from 'react-router-dom';
import LoadingWithProgress from '../components/LoadingWithProgress.tsx';
import { Box } from "@mui/material";
import { useGetClusterScoresMutation } from "../slices/api.tsx";
import { useToast } from "../components/ToastProvider.tsx";
import { extractHttpErrorMessage } from "../utils/extractHttpErrorMessage.tsx";
import { ClusterScore } from "../slices/scoresStructures.tsx";
import ClusterScoresTable from "../components/ScoreTable.tsx";
import { TopBar } from "../common/TopBar.tsx";

export const Audit = () => {
  const [searchParams] = useSearchParams();
  const clusterFullName = searchParams.get("cluster");
  const application_context = useContext(ApplicationContext);
  const { currentClusterOverview } = useContext(ApplicationContext);
  const [currentClusterScores, setCurrentClusterScores] = useState<ClusterScore>(undefined)
  const [getClusterScores] = useGetClusterScoresMutation();
  const { showError } = useToast();

  // Fetch the cluster scores. It is not loaded as part of the cluster overview data
  // because it is heavy to compute on the backend and is not needed in most cases.
  useEffect(() => {
    getClusterScores({ cluster: clusterFullName }).then((response) => {
      if (response.error) {
        showError({ summary: 'Error fetching cluster details', detail: extractHttpErrorMessage(response.error) });
        console.warn("No cluster scores found.", response.error);
      } else if (response.data) {
        setCurrentClusterScores(response.data as ClusterScore);
        console.log("Cluster scores:", response.data);
      }
    }
    ).catch((error) => {
      console.error('Error fetching cluster scores:', error);
    });
  }, [clusterFullName]);

  // Check if the current cluster overview is available and the alias matches the clusterName
  // If not, navigate to the correct cluster overview page. This is typically used to sync the URL
  // with the current cluster overview in the application context  after a side bar change.
  useEffect(() => {
    // Fetch data only if clusterFullName exists and it doesn't match the current overview alias
    if (clusterFullName && currentClusterOverview?.fullname !== clusterFullName) {
      application_context.fetchClusterAndNamespaceData(clusterFullName);
    }
  }, [clusterFullName, currentClusterOverview?.alias]);

  if (!currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
    return <PageBodyWrapper><LoadingWithProgress /></PageBodyWrapper>;
  }
  if (!currentClusterScores) {
    return <PageBodyWrapper><LoadingWithProgress /></PageBodyWrapper>;
  }
  console.log("currentClusterScores", currentClusterScores);
  return (
    <PageBodyWrapper>
      <TopBar
        title="Resource Scores"
        description="Review your cluster resource scores"
        backgroundUrl=""
      />
      <Box padding={4} paddingTop={12}>
        <ClusterScoresTable clusterScores={currentClusterScores} />
      </Box>
    </PageBodyWrapper>
  );
};
