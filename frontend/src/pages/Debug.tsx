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

/**
 * Debug component that displays the current cluster overview.
 *
 * This component uses the `useNavigate` hook from `react-router-dom` to navigate
 * to the correct cluster overview page if the `clusterName` from the URL parameters
 * does not match the `alias` of the `currentClusterOverview` from the application context.
 *
 * If the `currentClusterOverview` is not available or the `alias` does not match the `clusterName`,
 * a loading skeleton is displayed.
 *
 * @component
 * @returns {JSX.Element} The rendered component.
 *
 * @example
 * ```tsx
 * import Debug from './Debug';
 *
 * function App() {
 *   return (
 *     <Debug />
 *   );
 * }
 * ```
 */
import { useContext, useEffect } from "react";
import { ApplicationContext } from "../app/ApplicationContextProvider";
import { useNavigate, useParams } from "react-router-dom";
import LoadingWithProgress from "../components/LoadingWithProgress";

const Debug = () => {
  const navigate = useNavigate();
  const { currentClusterOverview } = useContext(ApplicationContext);
  const { clusterName } = useParams();

  // Check if the current cluster overview is available and the alias matches the clusterName
  // If not, navigate to the correct cluster overview page. This is typically used to sync the URL
  // with the current cluster overview in the application context  after a side bar change.
  useEffect(() => {
    if (currentClusterOverview?.alias !== clusterName) {
      navigate(`/debug/${currentClusterOverview?.alias}`, { replace: true });
    }
  }, [clusterName, currentClusterOverview]);

  if (!currentClusterOverview || currentClusterOverview?.alias !== clusterName) {
    return <LoadingWithProgress />;
  }

  return (
    <>
      <h1>DEBUG PAGE </h1>
      <h2>Cluster Name: {currentClusterOverview.alias}</h2>
    </>
  );
};
export default Debug;
