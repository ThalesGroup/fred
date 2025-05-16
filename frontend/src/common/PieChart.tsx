import Box from "@mui/material/Box";
import { CircularProgress, Typography, useTheme } from "@mui/material";
import EChartsReact from "echarts-for-react";  // Import EChartsReact
import { useNavigate } from 'react-router-dom';

export interface ChartOptions {
    tooltip: Object;
    legend: Object;
    series: Object[];
}
interface PieChartProps {
    data: { alias: string, fullname: string; value: number }[];
    unit: string;
}
export const PieChart = ({data, unit}: PieChartProps) => {
    const theme = useTheme();
    const navigate = useNavigate();  // For navigation on slice click

    const onPieSliceClick = (params: { name : string; data: { fullname: string }}) => {
        navigate(`/inspect?cluster=${params.data.fullname}`);  // Navigate to the inspect page with the selected slice
    };

    const renderOptions = (): ChartOptions => {
        if (data.length === 0) return {} as ChartOptions;

        return {
            tooltip: {
                trigger: 'item',
                formatter: `{b} : {c} ${unit} ({d}%)`
            },
            legend: {
                show: false,
                orient: 'vertical',
                right: 10,
                top: 'middle',
                data: data.map((cluster) => cluster.alias),
                selectedMode: false,
                textStyle: {
                    color: theme.palette.text.primary,  // Apply the primary text color to the legend text
                },
            },
            series: [
                {
                    type: 'pie',
                    radius: '90%',
                    center: ['50%', '50%'],
                    selectedMode: false,
                    data: data.map((cluster) => ({
                        name: cluster.alias,
                        fullname: cluster.fullname,
                        value: cluster.value,
                        itemStyle: {
                            borderColor: '#fff',  // White border around each slice
                            borderWidth: 1,  // Width of the border
                        },
                    })),
                    labelLine: {
                        show: true,
                    },
                    label: {
                        show: true,
                        color: theme.palette.text.primary,  // Set the label color based on the theme
                    },
                }
            ],
        };
    };

    return (
        <Box height="100%" width="100%">
            {data.length > 0 ? (
                <EChartsReact
                    option={renderOptions()}  // Pass chart options
                    onEvents={{
                        'click': onPieSliceClick  // Attach click event to handle navigation
                    }}
                    style={{ height: '100%', width: '100%' }}  // Chart styling
                />
            ) : (
                <>
                    <Typography>Waiting for data ...</Typography>
                    <CircularProgress />
                </>
            )}
        </Box>
    );
}
