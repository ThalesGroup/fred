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

import { Button, Grid2, Skeleton, Typography, useTheme } from "@mui/material";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import 'dayjs/locale/en-gb';
import { useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FootprintContext } from "../app/FootprintContextProvider.tsx";
import { ClusterMiniature } from "./ClusterMiniature.tsx";

dayjs.extend(utc);
dayjs.extend(timezone);

export const ClusterFilter = () => {

    const inspect_ctx = useContext(FootprintContext);
    const navigate = useNavigate();
    const [selectAll, setSelectAll] = useState(false);
    const theme = useTheme();

    // Callback to handle the selection/unselection of a cluster
    // to update the global indicators.
    const handleSelectUnselectCluster = (fullname: string) => {
        inspect_ctx.updateClusterFootprints(fullname);
    }
    // Callback to handle the selection of a cluster to see its details.
    const handleFollowSelectedCluster = (fullname: string) => {
        navigate(`/inspect?cluster=${fullname}`);
    }
    useEffect(() => {
        setSelectAll(inspect_ctx.allClusterFootprints.length !== inspect_ctx.selectedClusterFootprints.length);
    }, [inspect_ctx.selectedClusterFootprints, inspect_ctx.allClusterFootprints]);



    const handleSelectAll = () => {
        if (selectAll) {
            inspect_ctx.updateSelectedClusterFootprints(inspect_ctx.allClusterFootprints);
        } else {
            inspect_ctx.updateSelectedClusterFootprints([]);
        }
        setSelectAll(!selectAll);
    };
    return (
        <Grid2
            p={2}
            container
            direction="column"
            justifyContent="space-between" // Space between the clusters and the button
            sx={{ height: '90%' }} // Full height for the enclosing container
        >
            {/* Cluster Miniatures */}
            <Grid2 container spacing={2} justifyContent="center" sx={{ flexGrow: 0 }}>
                {inspect_ctx.allClusterFootprints.length > 0 ? (
                    inspect_ctx.allClusterFootprints.map((clusterFootprint, index) => (
                        <Grid2
                            key={index}
                            container
                            justifyContent="center"
                            sx={{ flexGrow: 0 }} // Prevent full height for each item
                        >
                            <ClusterMiniature
                                fullname={clusterFootprint.cluster.fullname}
                                provider={clusterFootprint.cluster.provider}
                                alias={clusterFootprint.cluster.alias}
                                hadleSelectUnselect={handleSelectUnselectCluster}
                                handleFollowSelected={handleFollowSelectedCluster}
                                activate={inspect_ctx.selectedClusterFootprints.includes(clusterFootprint)}
                            />
                        </Grid2>
                    ))
                ) : (
                    <Skeleton animation="wave" width="100%" height="100%" />
                )}
            </Grid2>

            {/* Select/Unselect Button */}
            <Grid2 sx={{ marginTop: "auto" }}> {/* Push button to bottom */}
                <Button
                    onClick={() => handleSelectAll()}
                    sx={{
                        backgroundColor: theme.palette.primary.main,
                        color: theme.palette.primary.contrastText,
                        border: 'none',
                        textTransform: 'none',
                        '&:hover': {
                            backgroundColor: theme.palette.background.default,
                            textDecoration: 'underline',
                        },
                    }}
                >
                    <Typography color={theme.palette.primary.contrastText} variant="body2">
                        {selectAll ? 'Select all' : 'Unselect all'}
                    </Typography>
                </Button>
            </Grid2>
        </Grid2>
    );
}
