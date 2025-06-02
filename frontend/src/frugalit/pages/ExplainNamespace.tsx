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

import { useSearchParams } from "react-router-dom";
import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import { Box } from "@mui/material";
import { useContext, useEffect, useState } from "react";
import { ApplicationContext } from "../../app/ApplicationContextProvider.tsx";
import { useGetNamespaceFactsMutation, useGetNamespaceSummaryMutation } from "../slices/api.tsx";
import { createFactList, FactList } from "../slices/factsStructures.tsx";
import { NamespaceSummary } from "../slices/namespaceSummaryStructures.tsx";
import { NamespaceCard } from "../component/NamespaceCard.tsx";
import LoadingWithProgress from "../../components/LoadingWithProgress.tsx";

async function fetchNamespaceData({ cluster, namespace, getSummary, getFacts }) {
  const [summaryRes, factsRes] = await Promise.all([
    getSummary({ cluster: cluster, namespace: namespace }),
    getFacts({ cluster: cluster, namespace: namespace }),
  ]);
  const summary = summaryRes.data || {};
  const facts = factsRes.data || [];
  return { summary, facts };
}
export const ExplainNamespace = () => {
  const [searchParams] = useSearchParams();
  const clusterFullName = searchParams.get("cluster");
  const namespace = searchParams.get("namespace");
  const [getNamespaceSummary] = useGetNamespaceSummaryMutation();
  const [getNamespaceFacts] = useGetNamespaceFactsMutation();
  const applicationContext = useContext(ApplicationContext);
  const { currentClusterOverview } = useContext(ApplicationContext);
  const [namespaceFacts, setNamespaceFacts] = useState<FactList | undefined>(undefined);
  const [namespaceSummary, setNamespaceSummary] = useState<NamespaceSummary | undefined>(undefined);

  const loadNamespaceData = async (clusterFullName: string, namespace: string) => {
    // Clear current resource data
    setNamespaceSummary(namespaceSummary);
    setNamespaceFacts(createFactList());

    const fetcher = {
      getSummary: getNamespaceSummary,
      getFacts: getNamespaceFacts,
    };
    const { summary, facts } = await fetchNamespaceData({
      cluster: clusterFullName,
      namespace: namespace,
      ...fetcher,
    });
    setNamespaceFacts(facts);
    setNamespaceSummary(summary);
  };
  useEffect(() => {
    if (!currentClusterOverview && namespace) {
      // Load the cluster and namespace data
      applicationContext.fetchClusterAndNamespaceData(clusterFullName);
    }
    if (currentClusterOverview && namespace) {
      loadNamespaceData(clusterFullName, namespace);
    }
  }, [clusterFullName, namespace, currentClusterOverview]); // Trigger when 'cluster' changes
  console.log("Namespace", namespace);
  console.log("ClusterFullName", clusterFullName);
  console.log("CurrentClusterOverview", currentClusterOverview);
  if (!currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
    return (
      <PageBodyWrapper>
        <LoadingWithProgress />
      </PageBodyWrapper>
    );
  }
  return (
    <PageBodyWrapper>
      <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" minHeight="50vh">
        <NamespaceCard
          cluster={currentClusterOverview}
          factList={namespaceFacts}
          summary={namespaceSummary}
          namespace={namespace}
        />
      </Box>
    </PageBodyWrapper>
  );
};
