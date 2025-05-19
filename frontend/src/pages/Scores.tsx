import { useParams, useLocation } from 'react-router-dom';
import { Typography } from '@mui/material';
import { PageBodyWrapper } from '../common/PageBodyWrapper';
import { ResourceScoreDetailRadarChart } from '../frugalit/component/ResourceScoreDetailRadarChart';
import { WorkloadScores } from '../frugalit/slices/scoresStructures';

const mapScoresToAttributes = (scores: WorkloadScores) => {
    return Object.entries(scores).map(([key, { score, reason }]) => ({
        attribut_name: key,
        display_text: `${key.toUpperCase()}`, // Include reason with the attribute name
        value: score * 10, // Scale score for radar chart (optional)
        reason: reason
    }));
};
export const Scores = () => {
    const { cluster, namespace, application } = useParams();  // Get URL params
    const location = useLocation();
    const score = location.state?.score as WorkloadScores | undefined;  // Get score from location.state if passed

    // TODO: Fetch or handle score data if it's not passed through state
    if (!score) {
        console.log(" state not defined", cluster, namespace, application);
        return <Typography variant="body2">Score data not available. Please navigate through the main view.</Typography>;
    }

    return (
        <PageBodyWrapper>
           
            <ResourceScoreDetailRadarChart
                            zoom={"50%"}
                            application_name={application}
                            data={mapScoresToAttributes(score)}
                            unit={"/100"}
                        />
        </PageBodyWrapper>
    );
};
