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
import { ApplicationContext } from "../app/ApplicationContextProvider.tsx";

/**
 * Custom hook to fetch cluster and namespace data
 * @param clusterName The name of the cluster to fetch data for
 */
export const useCluster = (clusterName: string | undefined) => {
  const global_context = useContext(ApplicationContext);
  const [isFetching, setIsFetching] = useState(false); // Add a fetching flag to prevent redundant fetches

  useEffect(() => {
    if (clusterName && !isFetching) {
      // Check if the clusterName is already the current cluster to avoid re-fetching
      if (global_context.currentClusterOverview?.alias === clusterName) {
        return;
      }

      console.log("Fetching data for cluster", clusterName);
      setIsFetching(true); // Mark as fetching to avoid multiple fetches

      // Call fetchClusterAndNamespaceData and use .finally()
      global_context.fetchClusterAndNamespaceData(clusterName)
        .finally(() => {
          setIsFetching(false); // Reset fetching flag when done
        });
    }
  }, [clusterName, global_context]); // Ensure the effect only triggers when the clusterName changes
};
