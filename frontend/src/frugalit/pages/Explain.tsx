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

import { useContext, useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApplicationContext } from "../../app/ApplicationContextProvider.tsx";
import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import { Theme, useTheme } from "@mui/material";
import LoadingWithProgress from "../../components/LoadingWithProgress.tsx";
import { ClusterDescription } from "../slices/api.tsx";
import { TopBar } from "../../common/TopBar.tsx";

export const Explain = () => {
  const [searchParams] = useSearchParams();
  const clusterFullName = searchParams.get("cluster");
  const theme = useTheme<Theme>();
  const application_context = useContext(ApplicationContext);
  const { currentClusterOverview, currentClusterDescription } = useContext(ApplicationContext);
  const navigate = useNavigate();
  const [treeData, setTreeData] = useState([]);
  const [loading, setLoading] = useState(true);

  // Check if the current cluster overview is available and the alias matches the clusterName
  // If not, navigate to the correct cluster overview page. This is typically used to sync the URL
  // with the current cluster overview in the application context  after a side bar change.
  useEffect(() => {
    if (currentClusterOverview?.fullname !== clusterFullName) {
      application_context.fetchClusterAndNamespaceData(clusterFullName);
    }
  }, [clusterFullName, currentClusterOverview]);

  function buildTreeData(currentCluster: ClusterDescription) {
    if (!currentCluster) {
      return [];
    }
    const namespaces = currentCluster.namespaces.map((namespace) => ({
      name: namespace.name,
      fullname: currentCluster.cluster,
      type: "namespace",
      children: namespace.workloads.map((resource) => ({
        name: resource.name,
        fullname: currentCluster.cluster,
        namespace: namespace.name,
        type: "resource",
      })),
    }));
    return [
      {
        name: currentCluster.alias,
        fullname: currentCluster.cluster,
        type: "cluster",
        children: namespaces,
      },
    ];
  }

  useEffect(() => {
    if (currentClusterDescription) {
      const data = buildTreeData(currentClusterDescription);
      setTreeData(data);
      setLoading(false); // Set loading to false when data is ready
    }
  }, [currentClusterDescription]);

  const handleTreeClick = (params) => {
    if (params.data.type === "cluster") {
      navigate(`/explain-cluster?cluster=${params.data.fullname}`);
    } else if (params.data.type === "namespace") {
      navigate(`/explain-namespace?cluster=${params.data.fullname}&namespace=${params.name}`);
    } else {
      navigate(
        `/explain-workload?cluster=${params.data.fullname}&namespace=${params.data.namespace}&workload=${params.name}`,
      );
    }
  };

  const getOption = () => ({
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
    },
    series: [
      {
        type: "tree",
        data: treeData,
        top: "10%",
        left: "10%",
        bottom: "10%",
        right: "30%",
        symbol: "none",
        symbolSize: 20,
        layout: "orthogonal",
        label: {
          position: "inside",
          verticalAlign: "middle",
          align: "center",
          fontSize: theme.typography.caption.fontSize,
          fontFamily: theme.typography.fontFamily,
          color: theme.palette.primary.contrastText,
          padding: [5, 5],
          backgroundColor: theme.palette.primary.main,
          borderColor: theme.palette.primary.contrastText,
          borderWidth: 1,
          borderRadius: 4,
        },
        leaves: {
          label: {
            position: "right",
            verticalAlign: "middle",
            align: "left",
            backgroundColor: theme.palette.primary.main,
            fontSize: theme.typography.caption.fontSize,
            fontFamily: theme.typography.fontFamily,
            color: theme.palette.primary.contrastText,
            borderWidth: 1,
            borderRadius: 4,
          },
        },
        emphasis: {
          focus: "descendant",
        },
        lineStyle: {
          width: 2,
          color: theme.palette.primary.light,
          curveness: 0, // Set curveness to 0 for straight lines
        },
        edgeShape: "polyline",
        edgeForkPosition: "50%",
        expandAndCollapse: false,
        animationDuration: 550,
        animationDurationUpdate: 550,
      },
    ],
  });
  if (loading || !currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
    return (
      <PageBodyWrapper>
        <LoadingWithProgress />
      </PageBodyWrapper>
    );
  }
  return (
    <PageBodyWrapper>
      <TopBar
        title="Cluster Overview"
        description="Navigate your selected cluster and its resources"
        backgroundUrl=""
      ></TopBar>
      <ReactECharts
        option={getOption()}
        onEvents={{ click: handleTreeClick }}
        style={{ height: "100%", width: "100%" }}
      />
    </PageBodyWrapper>
  );
};
