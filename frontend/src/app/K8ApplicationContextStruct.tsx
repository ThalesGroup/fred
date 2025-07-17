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

import { ClusterDescription, ClusterOverview } from "../frugalit/slices/api.tsx";
import { DurationPrecision } from "../utils/period.tsx";

/**
 * The Application context keeps track of all the clusters known to frugal IT.
 * If a cluster is selected as the current cluster, its namespaces will be
 * loaded.
 *
 * These two levels cluster and namespaces are shared among components.
 */
export interface K8ApplicationContextStruct {
  /**
   * The currently selected cluster overview. It displays only the identification information
   * of the current cluster.
   */
  currentClusterOverview: ClusterOverview;

  /**
   * The details of the currently selected cluster. It contains more detailed information
   * such as the list of namespaces each with the list of resources.
   */
  currentClusterDescription: ClusterDescription;

  /**
   * A list of all available clusters.
   */
  allClusters: ClusterOverview[];

  /**
   * The list of namespaces from the currently selected cluster.
   */
  currentNamespaces: string[];

  /**
   * A list of selected namespaces.
   * @todo: This must be moved to the Inspect page component.
   */
  selectedNamespaces: string[];

  /**
   * The current precision setting (e.g. seconds, minutes, hours, etc.).
   */
  currentPrecision: DurationPrecision;

  /**
   * Updates the currently selected cluster.
   * @param cluster The new cluster to select.
   */
  updateCurrentCluster: (cluster: ClusterOverview) => void;

  /**
   * Updates the list of all available clusters.
   * @param clusters The new list of clusters.
   */
  updateAllClusters: (clusters: ClusterOverview[]) => void;

  /**
   * Updates the list of selected namespaces.
   * @param namespace The new list of selected namespaces.
   */
  updateSelectedNamespaces: (namespace: string[]) => void;

  /**
   * Adds or removes a single namespace from the list of selected namespaces.
   * @param namespace The namespace to add or remove.
   */
  updateSingleNamespace: (namespace: string) => void;

  /**
   * Updates the current precision setting.
   * @param precision The new precision setting.
   */
  updateCurrentPrecision: (precision: DurationPrecision) => void;

  /**
   * Fetches data for a specific cluster and its namespaces.
   * @param clusterFullName The full name of the cluster to fetch data for.
   */
  fetchClusterAndNamespaceData: (clusterFullName: string) => Promise<void>;
}
