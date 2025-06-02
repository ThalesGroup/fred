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

import Box from "@mui/material/Box";
import { IconButton, Grid2, Paper, useTheme, Drawer } from "@mui/material";
import ReactECharts from "echarts-for-react";
import MarkdownRenderer from "../../components/markdown/MarkdownRenderer";
import CropFreeIcon from "@mui/icons-material/CropFree";
import { useState } from "react";

const truncateMarkdown = (content: string, maxLength: number) => {
  return content.length > maxLength ? content.substring(0, maxLength) + " ..." : content;
};
export const ResourceScoreDetailRadarChart = (props: {
  data: {
    attribut_name: string;
    display_text: string;
    value: number;
    reason: string;
  }[];
  unit: string;
  application_name: string;
  zoom: string;
}) => {
  const theme = useTheme();
  const valuesSerie: number[] = [];
  const [open, setOpen] = useState(false);
  const [summaryContent, setSummaryContent] = useState<string>("");
  const handleOpenSummary = (content: string) => {
    setSummaryContent(content);
    setOpen(true);
  };
  const handleCloseSummary = () => {
    setOpen(false);
  };

  const indicators = props.data.map((attribut) => ({
    name: attribut.display_text, // Use display_text, which includes the reason
    max: 100,
  }));

  props.data.forEach((attribut) => valuesSerie.push(attribut.value));

  const renderOptions = () => {
    if (props.data.length === 0) return {};

    const opt = {
      radar: {
        radius: props.zoom,
        indicator: indicators,
        name: {
          textStyle: {
            color: theme.palette.text.primary,
            fontSize: 10, // Adjust font size to fit longer text
            lineHeight: 15, // Increase line height to allow multiline text
            overflow: "truncate", // Optional: truncate if text overflows
          },
          formatter: (name: string) => name.replace(/\n/g, "\n"), // Ensure newlines for readability
        },
        splitArea: {
          show: true,
          areaStyle: {
            color: [theme.palette.chart.alterningBgColor1, theme.palette.chart.alterningBgColor2],
          },
        },
      },
      series: [
        {
          name: "Score of the application",
          type: "radar",
          lineStyle: {
            color: theme.palette.chart.secondary,
            width: 2,
          },
          areaStyle: {
            color: theme.palette.chart.customAreaStyle,
            opacity: 0.5,
          },
          data: [
            {
              value: valuesSerie,
              name: props.application_name,
            },
          ],
          symbol: "circle",
          symbolSize: 8,
          itemStyle: {
            color: theme.palette.chart.secondary,
            borderColor: theme.palette.chart.primary,
            borderWidth: 2,
          },
          emphasis: {
            itemStyle: {
              color: theme.palette.error.main,
              borderColor: theme.palette.warning.main,
              borderWidth: 3,
            },
          },
        },
      ],
    };
    return opt;
  };

  return (
    <Box display="flex" flexDirection="column" alignItems="center" p={2} height="100%">
      {/* Render Radar Chart in the Center */}
      <Box sx={{ height: "70%", width: "100%" }}>
        <ReactECharts
          option={renderOptions()}
          style={{ height: "100%", width: "100%", padding: 0, margin: 0 }} // Remove padding/margin on ReactECharts
          opts={{ renderer: "svg" }}
        />
      </Box>

      {/* Render Labels Around the Chart */}
      <Grid2 container spacing={2} justifyContent="center">
        {props.data.map((attribut, index) => (
          <Grid2 size={{ xs: 12, sm: 6, md: 4 }} key={index}>
            <Paper sx={{ p: 2, width: "100%", position: "relative" }}>
              <MarkdownRenderer
                content={`## ${attribut.display_text}\n${truncateMarkdown(attribut.reason, 500)}`}
                size="small"
              />
              <IconButton
                sx={{ position: "absolute", top: 8, right: 8 }}
                onClick={() => handleOpenSummary(attribut.reason)}
              >
                <CropFreeIcon />
              </IconButton>
            </Paper>
          </Grid2>
        ))}
      </Grid2>
      <Drawer anchor="right" open={open} onClose={handleCloseSummary}>
        <Box sx={{ width: "50vw", p: 2 }}>
          <Paper sx={{ p: 1, px: 2, width: "100%" }}>
            <MarkdownRenderer size="medium" content={summaryContent} />
          </Paper>
        </Box>
      </Drawer>
    </Box>
  );
};
