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

import { Box } from "@mui/material";
import { useContext, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ApplicationContext } from "../../app/ApplicationContextProvider.tsx";
import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import FactsHexagonChart from "../component/FactsHexagonChart.tsx";
import LoadingWithProgress from "../../components/LoadingWithProgress.tsx";
import { TopBar } from "../../common/TopBar.tsx";

export const Facts = () => {
  const [searchParams] = useSearchParams();
  const clusterFullName = searchParams.get("cluster");
  const application_context = useContext(ApplicationContext);
  const { currentClusterOverview, currentClusterDescription } = application_context;

  useEffect(() => {
    if (currentClusterOverview?.fullname !== clusterFullName) {
      application_context.fetchClusterAndNamespaceData(clusterFullName);
    }
  }, [clusterFullName, currentClusterOverview, application_context]);

  if (!currentClusterDescription) {
    return (
      <PageBodyWrapper>
        <LoadingWithProgress />
      </PageBodyWrapper>
    );
  }

  return (
    <PageBodyWrapper>
      <TopBar title="Facts Overview" 
        description="Monitor and analyze your cluster's facts" />
      <Box
        sx={{
          padding: 8,
          height: "100%", // Ensure the Box takes the full height of its parent
          display: "flex", // Use flexbox to manage child layout
          justifyContent: "center", // Center the chart horizontally
          alignItems: "center", // Center the chart vertically
        }}
      >
        <FactsHexagonChart clusterDescription={currentClusterDescription} />
      </Box>
    </PageBodyWrapper>
  );
};
