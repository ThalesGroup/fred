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

import { useMemo, useState } from "react";
import {
  Box,
  Typography,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  TableContainer,
  Chip,
  TablePagination,
} from "@mui/material";
import { LLMMetric } from "./metricsType";
import DashboardCard from "./DashboardCard";

type Props = {
  metrics: LLMMetric[];
};

export default function MetricTable({ metrics }: Props) {
  const [userFilter, setUserFilter] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  const uniqueUsers = useMemo(() => {
    const users = new Set(metrics.map(m => m.user_id));
    return Array.from(users);
  }, [metrics]);

  const filteredMetrics = useMemo(() => {
    return userFilter === "all"
      ? metrics
      : metrics.filter(m => m.user_id === userFilter);
  }, [metrics, userFilter]);

  const paginatedMetrics = useMemo(() => {
    const start = page * rowsPerPage;
    return filteredMetrics.slice(start, start + rowsPerPage);
  }, [filteredMetrics, page, rowsPerPage]);

  const handleChangePage = (_: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  return (
    <DashboardCard title="Recent Calls">
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h6">Recent Calls</Typography>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Filter by user</InputLabel>
          <Select
            value={userFilter}
            onChange={e => {
              setUserFilter(e.target.value);
              setPage(0); // Reset page when filter changes
            }}
            label="Filter by user"
          >
            <MenuItem value="all">All Users</MenuItem>
            {uniqueUsers.map(user => (
              <MenuItem key={user} value={user}>
                {user}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell><strong>Time</strong></TableCell>
              <TableCell><strong>User</strong></TableCell>
              <TableCell><strong>Model</strong></TableCell>
              <TableCell align="right"><strong>Latency (s)</strong></TableCell>
              <TableCell align="right"><strong>Tokens</strong></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {paginatedMetrics.length > 0 ? (
              paginatedMetrics.map((m, idx) => (
                <TableRow
                  key={idx}
                  hover
                  sx={{
                    backgroundColor: m.latency > 5 ? "rgba(255, 0, 0, 0.05)" : "inherit",
                  }}
                >
                  <TableCell>{new Date(m.timestamp * 1000).toLocaleTimeString()}</TableCell>
                  <TableCell>
                    <Chip label={m.user_id} variant="outlined" size="small" />
                  </TableCell>
                  <TableCell>{m.model_type}</TableCell>
                  <TableCell align="right" sx={{ color: m.latency > 5 ? "error.main" : "inherit" }}>
                    {m.latency.toFixed(2)}
                  </TableCell>
                  <TableCell align="right">{m.token_usage.total_tokens}</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <Typography variant="body2" color="text.secondary">
                    No data available for this user.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <TablePagination
        component="div"
        count={filteredMetrics.length}
        page={page}
        onPageChange={handleChangePage}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={handleChangeRowsPerPage}
        rowsPerPageOptions={[5, 10, 20, 50]}
      />
    </DashboardCard>
  );
}
