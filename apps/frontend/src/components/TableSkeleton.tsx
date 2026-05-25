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

import { Box, Skeleton, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from "@mui/material";

interface TableSkeletonColumn {
  width?: number | string;
  padding?: "normal" | "checkbox";
  hasIcon?: boolean;
}

interface TableSkeletonProps {
  columns: TableSkeletonColumn[];
  rows?: number;
}

export const TableSkeleton = ({ columns, rows = 5 }: TableSkeletonProps) => {
  return (
    <TableContainer>
      <Table>
        <TableHead>
          <TableRow>
            {columns.map((column, index) => (
              <TableCell key={index} padding={column.padding}>
                {column.padding === "checkbox" ? (
                  <Skeleton variant="rectangular" width={20} height={20} />
                ) : (
                  <Skeleton variant="text" width={column.width || 100} />
                )}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {[...Array(rows)].map((_, rowIndex) => (
            <TableRow key={rowIndex}>
              {columns.map((column, colIndex) => (
                <TableCell key={colIndex} padding={column.padding}>
                  {column.padding === "checkbox" ? (
                    <Skeleton variant="rectangular" width={20} height={20} />
                  ) : (
                    <Box display="flex" alignItems="center" gap={1}>
                      {column.hasIcon && <Skeleton variant="rectangular" width={24} height={24} />}
                      <Skeleton variant="text" width={column.width || 100} />
                    </Box>
                  )}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};
