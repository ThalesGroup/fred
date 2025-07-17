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

import { useContext, useEffect } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { Skeleton } from "@mui/material";
import { K8ApplicationContext } from "../app/K8ApplicationContextProvider";

const withClusterSync = (Component) => {
  return (props) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { currentClusterOverview } = useContext(K8ApplicationContext);
    const { clusterName } = useParams();

    useEffect(() => {
      if (currentClusterOverview?.alias !== clusterName) {
        // Replace the current clusterName in the URL with the new one
        const updatedPath = location.pathname.replace(clusterName, currentClusterOverview?.alias);
        navigate(updatedPath);
      }
    }, [clusterName, currentClusterOverview, location.pathname, navigate]);

    if (!currentClusterOverview || currentClusterOverview?.alias !== clusterName) {
      return <Skeleton animation="wave" width={"80%"} height={"200px"} />;
    }

    return <Component {...props} />;
  };
};

export default withClusterSync;
