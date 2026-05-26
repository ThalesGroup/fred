import { Tabs, TabsProps } from "@mui/material";

/**
 * Decorated Tabs component with rounded pill-style appearance.
 */
export function RoundTabs(props: TabsProps) {
  return (
    <Tabs
      {...props}
      variant={props.variant ?? "fullWidth"}
      slotProps={{ indicator: { sx: { display: "none" } } }}
      sx={{
        alignSelf: "stretch",
        bgcolor: (theme) => theme.palette.action.hover,
        borderRadius: 999,
        p: 0.5,
        "& .MuiTab-root": {
          textTransform: "none",
          minHeight: 40,
          borderRadius: 999,
          fontWeight: 600,
          gap: 0.75,
        },
        "& .Mui-selected": {
          bgcolor: (theme) => theme.palette.background.paper,
          boxShadow: 1,
        },
        ...props.sx,
      }}
    />
  );
}
