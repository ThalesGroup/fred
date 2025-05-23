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

import { createContext, PropsWithChildren, useEffect, useState } from "react";
import {
  ClusterOverview,
  useGetClusterListMutation,
  useGetNamespaceListMutation,
  useGetClusterDescriptionMutation,
  ClusterDescription
} from "../frugalit/slices/api.tsx";
import { NamespaceList } from "../utils/namespace.tsx";
import { DurationPrecision } from "../utils/period.tsx";
import { ApplicationContextStruct } from "./ApplicationContextStruct.tsx";
import { useToast } from "../components/ToastProvider.tsx";
import { extractHttpErrorMessage } from "../utils/extractHttpErrorMessage.tsx";

/**
 * Our application context. 
 */
export const ApplicationContext = createContext<ApplicationContextStruct>(null!)
export const ApplicationContextProvider = (props: PropsWithChildren<{}>) => {
  const { showError } = useToast(); // Use the toast hook

  const [getClusterList] = useGetClusterListMutation();
  const [getNamespaceList] = useGetNamespaceListMutation();
  const [getClusterDescription] = useGetClusterDescriptionMutation();
  const [currentCluster, setCurrentCluster] = useState<ClusterOverview>(undefined)
  const [currentClusterDescription, setCurrentClusterDescription] = useState<ClusterDescription>(undefined)
  const [allClusters, setAllClusters] = useState<ClusterOverview[]>([])
  const [allNamespaces, setAllNamespaces] = useState<string[]>([])
  const [selectedNamespaces, setSelectedNamespaces] = useState<string[]>([])
  const [currentPrecision, setCurrentPrecision] = useState<DurationPrecision>(DurationPrecision.HOUR)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(true);
  // Load user preferences from local storage on app startup
  useEffect(() => {
    const storedSidebarState = localStorage.getItem('isSidebarCollapsed');
    const storedThemeMode = localStorage.getItem('darkMode');

    if (storedSidebarState !== null) {
      setIsSidebarCollapsed(JSON.parse(storedSidebarState));
    }
    if (storedThemeMode !== null) {
      setDarkMode(JSON.parse(storedThemeMode));
    }
  }, []);

  // Save sidebar state to local storage when it changes
  useEffect(() => {
    localStorage.setItem('isSidebarCollapsed', JSON.stringify(isSidebarCollapsed));
  }, [isSidebarCollapsed]);

  // Save dark mode preference to local storage when it changes
  useEffect(() => {
    localStorage.setItem('darkMode', JSON.stringify(darkMode));
  }, [darkMode]);

  const toggleSidebar = () => {
    setIsSidebarCollapsed((prevState) => !prevState);
  };

  const toggleDarkMode = () => {
    setDarkMode((prevState) => !prevState);
  };

  const contextValue: ApplicationContextStruct = {
    currentClusterOverview: currentCluster,
    currentClusterDescription: currentClusterDescription,
    allClusters: allClusters,
    currentNamespaces: allNamespaces,
    selectedNamespaces: selectedNamespaces,
    currentPrecision: currentPrecision,
    updateCurrentCluster: updateCurrentCluster,
    updateAllClusters: updateAllClusters,
    updateSelectedNamespaces: updateSelectedNamespaces,
    updateSingleNamespace: updateSingleNamespace,
    updateCurrentPrecision: updateCurrentPrecision,
    fetchClusterAndNamespaceData: fetchClusterAndNamespaceData,
    isSidebarCollapsed,
    darkMode,
    toggleSidebar,
    toggleDarkMode
  }

  function updateCurrentCluster(c: ClusterOverview): void {
    setCurrentCluster(c)
  }
  function updateAllClusters(a: ClusterOverview[]): void {
    setAllClusters(a)
  }

  function updateSelectedNamespaces(n: string[]): void {
    setSelectedNamespaces(n)
  }

  function updateSingleNamespace(n: string): void {
    if (selectedNamespaces.some(s => s === n)) {
      setSelectedNamespaces(prevState => prevState.filter(s => s !== n));
    } else {
      setSelectedNamespaces(prevState => [...prevState, n]);
    }
  }

  function updateCurrentPrecision(precision: DurationPrecision): void {
    setCurrentPrecision(precision)
  }

  function fetchNamespaceList(cluster: ClusterOverview): void {
    // Ensure that the passed cluster is of the correct type
    if (!cluster || typeof cluster !== 'object' || !('fullname' in cluster)) {
      showError({ summary: 'Invalid cluster provided', detail: 'Invalid cluster provided to fetchNamespaceList' });
      console.warn("Invalid cluster provided to fetchNamespaceList", cluster);
      return;
    }

    if (!cluster.fullname) {
      console.warn("Cluster has no fullname, skipping fetch for namespaces.", cluster);
      return;
    }

    setAllNamespaces([]);
    setSelectedNamespaces([]);

    // Fetch cluster facts. Facts are small and do not require backend computation
    // That's why we fetch them first.
    getClusterDescription({ cluster: cluster.fullname }).then((response) => {
      if (response.error) {
        showError({ summary: 'Error fetching cluster details', detail: extractHttpErrorMessage(response.error) });
        console.warn("No cluster details found.", response.error);
      } else if (response.data) {
        setCurrentClusterDescription(response.data as ClusterDescription);
        getNamespaceList({ cluster: cluster.fullname }).then((response) => {
          if (response.error) {
            showError({ summary: 'Error fetching namespaces', detail: extractHttpErrorMessage(response.error) });
            console.warn("No namespaces found.", response.error);
          } else if (response.data) {
            setAllNamespaces((response.data as NamespaceList).namespaces);
            setSelectedNamespaces((response.data as NamespaceList).namespaces);
          }
        });
      }
    }).catch((error) => {
      console.error('Error fetching cluster details:', error);
    });
  }


  async function fetchClusterAndNamespaceData(fullname: string) {
    console.log("APPLICATION CONTEXT fetchClusterAndNamespaceData", fullname);
    try {
      const clusterResponse = await getClusterList();
      if ('error' in clusterResponse) {
        showError({ summary: `Error loading cluster list`, detail: `Failed to load the known cluster list` });
        return;
      }

      const clusters = clusterResponse.data as ClusterOverview[];
      setAllClusters(clusters);

      // Find the selected cluster based on clusterName
      const selectedCluster = clusters.find((cluster) => cluster.fullname === fullname);
      if (!selectedCluster) {
        showError({ summary: 'Error setting current cluster', detail: `Cluster with name "${fullname}" not found.` });
        return;
      }

      // Set the current cluster
      updateCurrentCluster(selectedCluster);

      // Fetch namespaces for the selected cluster
      const namespaceResponse = await getNamespaceList({ cluster: selectedCluster.fullname }); // No extraOptions
      if ('error' in namespaceResponse) {
        return;
      }

      setAllNamespaces((namespaceResponse.data as NamespaceList).namespaces);
      setSelectedNamespaces((namespaceResponse.data as NamespaceList).namespaces);

      // Optionally, you can show success message after all data is fetched successfully
      // showSuccess({ summary: 'Loaded cluster and namespaces', detail: `Cluster and namespaces for "${clusterName}" loaded.` });

    } catch (error) {
      showError({ summary: 'Error fetching cluster and namespace data', detail: `${error}` });
    }
  }

  useEffect(() => {
    if (currentCluster) {
      fetchNamespaceList(currentCluster);
    }
  }, [currentCluster])

  // Fetch the cluster list on component mount and update the cluster and cluster states.
  useEffect(() => {
    getClusterList().then((response) => {
      if ("error" in response) {
        showError({ summary: `Error loading clusters list`, detail: extractHttpErrorMessage(response.error) });
      } else {
        setAllClusters(response.data as ClusterOverview[]);
      }
    })
  }, []);

  return <ApplicationContext.Provider value={contextValue}>{props.children}</ApplicationContext.Provider>
}


