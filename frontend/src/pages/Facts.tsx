import { Box } from '@mui/material';
import { useContext, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApplicationContext } from '../app/ApplicationContextProvider';
import { PageBodyWrapper } from '../common/PageBodyWrapper.tsx';
import FactsHexagonChart from '../components/FactsHexagonChart.tsx';
import LoadingWithProgress from '../components/LoadingWithProgress.tsx';
import { TopBar } from '../common/TopBar.tsx';


export const Facts = () => {
    const [searchParams] = useSearchParams();
    const clusterFullName = searchParams.get('cluster');
    const application_context = useContext(ApplicationContext);
    const { currentClusterOverview, currentClusterDescription } = application_context;

    useEffect(() => {
        if (currentClusterOverview?.fullname !== clusterFullName) {
            application_context.fetchClusterAndNamespaceData(clusterFullName);
        }
    }, [clusterFullName, currentClusterOverview, application_context]);

    if (!currentClusterDescription) {
        return <PageBodyWrapper><LoadingWithProgress /></PageBodyWrapper>;
    }

    return (
        <PageBodyWrapper>
            <TopBar     
                title="Facts Overview"
                description="Monitor and analyze your cluster's facts"
                backgroundUrl=""
            />
            <Box 
                sx={{
                    padding: 8,
                    height: '100%', // Ensure the Box takes the full height of its parent
                    display: 'flex', // Use flexbox to manage child layout
                    justifyContent: 'center', // Center the chart horizontally
                    alignItems: 'center', // Center the chart vertically
                }}>
                <FactsHexagonChart clusterDescription={currentClusterDescription} />
            </Box>
        </PageBodyWrapper>
    );
};
