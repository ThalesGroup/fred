import ExpandLess from "@mui/icons-material/ExpandLess";
import ExpandMore from "@mui/icons-material/ExpandMore";
import { Collapse, List, ListItemButton, ListItemIcon, ListItemText } from "@mui/material";
import { Fragment, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

export type SideBarNavigationElement = {
  key: string;
  label: string;
  icon: React.ReactNode;
  url?: string;
  children?: SideBarNavigationElement[];
};

interface SideBarNavigationListProps {
  menuItems: SideBarNavigationElement[];
  isSidebarOpen: boolean;
  indentation?: number;
}

export function SideBarNavigationList({ menuItems, isSidebarOpen, indentation = 0 }: SideBarNavigationListProps) {
  const location = useLocation();
  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>({});

  const isActive = (path: string) => {
    const menuPathBase = path.split("?")[0];
    const currentPathBase = location.pathname;
    return currentPathBase === menuPathBase || currentPathBase.startsWith(menuPathBase + "/");
  };

  const isAnyChildActive = (children?: SideBarNavigationElement[]) => !!children?.some((c) => c.url && isActive(c.url));

  useEffect(() => {
    setOpenKeys((prev) => {
      const next = { ...prev };
      for (const it of menuItems) {
        if (it.children && isAnyChildActive(it.children)) {
          next[it.key] = true;
        }
      }
      return next;
    });
  }, [location.pathname]);

  return (
    <List
      sx={{
        px: 1,
        // Add margin bottom between items except the last one
        "& > :not(:last-child)": { mb: 0.25 },
      }}
    >
      {menuItems.map((item) => {
        const hasChildren = !!(item.children && item.children.length > 0);
        const hasLink = !!item.url;
        const isOpen = openKeys[item.key] || false;
        const active = item.url ? isActive(item.url) : isAnyChildActive(item.children);

        return (
          <Fragment key={item.key}>
            <ListItemButton
              selected={active}
              dense
              component={hasLink ? Link : "div"}
              {...(hasLink ? { to: item.url } : {})}
              onClick={
                hasChildren ? () => setOpenKeys((prev) => ({ ...prev, [item.key]: !prev[item.key] })) : undefined
              }
              sx={{
                pl: 2 + indentation * 2,
                borderRadius: 2,
              }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText
                primary={item.label}
                slotProps={{
                  primary: {
                    sx: {
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    },
                  },
                }}
              />
              {hasChildren && (isOpen ? <ExpandLess /> : <ExpandMore />)}
            </ListItemButton>

            {item.children && item.children.length > 0 && (
              <Collapse in={isSidebarOpen && isOpen} timeout="auto" unmountOnExit>
                <SideBarNavigationList
                  menuItems={item.children}
                  isSidebarOpen={isSidebarOpen}
                  indentation={indentation + 1}
                />
              </Collapse>
            )}
          </Fragment>
        );
      })}
    </List>
  );
}
