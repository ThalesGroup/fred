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
import { useContext, useEffect } from 'react';
import { ApplicationContext } from '../../app/ApplicationContextProvider';
import { useSearchParams } from 'react-router-dom';
import { PageBodyWrapper } from '../../common/PageBodyWrapper';
import LoadingWithProgress from '../../components/LoadingWithProgress';
import { ClusterConsumption } from '../slices/api';
import { FootprintContext } from '../../app/FootprintContextProvider';
import { Box, Grid2, Theme, useTheme } from '@mui/material';
import { PeriodPicker } from '../component/PeriodPicker';
import { ChartCard } from '../../common/ChartCard';
import { transformClusterConsumptionToSerie } from '../../utils/serie';
import { NamespaceFilter } from '../../common/NamespaceFilter';
import { InspectCard } from '../../common/InspectCard';

const Inspect = () => {
    const [searchParams] = useSearchParams();
    const clusterFullName = searchParams.get("cluster");
    const { currentClusterOverview, selectedNamespaces} = useContext(ApplicationContext);
    const inspect_context = useContext(FootprintContext);
    const application_context = useContext(ApplicationContext);
    const theme = useTheme<Theme>();

    // Check if the current cluster overview is available and the alias matches the clusterName
    // If not, navigate to the correct cluster overview page. This is typically used to sync the URL
    // with the current cluster overview in the application context  after a side bar change.
    useEffect(() => {
        if (currentClusterOverview?.fullname !== clusterFullName) {
            application_context.fetchClusterAndNamespaceData(clusterFullName);
        }
    }, [clusterFullName, currentClusterOverview]);

    const getNamespacesFootprint = (footprint: ClusterConsumption) => {
        if (!selectedNamespaces || !footprint) {
            return [];
        }
        return selectedNamespaces.map((selectedNamespace: string) => (
            footprint.details.find((detail) => detail.name === selectedNamespace)
        )).filter(detail => detail !== undefined).map(detail => ({ alias: detail.name, fullname: "toto", value: detail.values.map(value => value).reduce((sum, value) => sum + value, 0) }))
    }
    if (!currentClusterOverview || currentClusterOverview?.fullname !== clusterFullName) {
        return <PageBodyWrapper><LoadingWithProgress/></PageBodyWrapper>;
    }

    return (
        <PageBodyWrapper>
            <Grid2 container spacing={4} p={2} >
                 <Grid2 container
                    justifyContent="space-between" alignItems="center"
                    size={12}
                    spacing={4}>
                    <PeriodPicker></PeriodPicker>
                </Grid2> 
              <Grid2 size={{ xs: 12 }}>
                    <Box width="100%">
                        <ChartCard
                            data={{
                                name: 'name',
                                color: 'color',
                                unit: 'cm',
                                serieTypes: [{
                                    logos: ['cost_circle', 'cost_white'],
                                    color: theme.palette.chart.highBlue,
                                    series: inspect_context.currentCostConsumption ? [transformClusterConsumptionToSerie(inspect_context.currentCostConsumption, 'Total charge', theme.palette.chart.highBlue)] : []
                                },
                                {
                                    logos: ['carbon_circle', 'carbon_white'],
                                    color: theme.palette.chart.highGreen,
                                    series: inspect_context.currentCarbonConsumption ? [transformClusterConsumptionToSerie(inspect_context.currentCarbonConsumption, 'Estimated Carbon footprint', theme.palette.chart.highGreen)] : []
                                },
                                {
                                    logos: ['energy_circle', 'energy_white'],
                                    color: theme.palette.chart.highYellow,
                                    series: inspect_context.currentEnergyConsumption ? [transformClusterConsumptionToSerie(inspect_context.currentEnergyConsumption, 'Esitmated Energy footprint', theme.palette.chart.highYellow)] : []
                                }]
                            }}
                            height="25vh"
                            type="bar"
                        />
                    </Box>
                </Grid2> 
                 <Grid2 size={{ xs: 12 }}>
                    <NamespaceFilter></NamespaceFilter>
                </Grid2> 
                <Grid2 container size={{ xs: 12 }} spacing={2}>
                    <Grid2 size={{ xs: 12, lg: 6 }}>
                        <InspectCard
                            title="Estimated carbon footprint"
                            logo='carbon_circle'
                            clusters={getNamespacesFootprint(inspect_context.currentCarbonConsumption)}
                            unit={inspect_context.currentCarbonConsumption ? inspect_context.currentCarbonConsumption.unit : null}
                        ></InspectCard>
                    </Grid2>
                    <Grid2 size={{ xs: 12, lg: 6 }}>
                        <InspectCard
                            title="Estimated energy footprint"
                            logo='energy_circle'
                            clusters={getNamespacesFootprint(inspect_context.currentEnergyConsumption)}
                            unit={inspect_context.currentEnergyConsumption ? inspect_context.currentEnergyConsumption.unit : null}
                        ></InspectCard>
                    </Grid2>
                </Grid2> 
            </Grid2>
        </PageBodyWrapper>
    );
};
export default Inspect;
