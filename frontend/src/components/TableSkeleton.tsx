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
