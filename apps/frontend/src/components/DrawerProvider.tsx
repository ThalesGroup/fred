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

import React, { createContext, useContext, useState, ReactNode } from "react";
import { Drawer } from "@mui/material";

interface DrawerConfig {
  content: ReactNode;
  anchor?: "left" | "right" | "top" | "bottom";
  onClose?: () => void;
}

interface DrawerContextType {
  openDrawer: (config: DrawerConfig) => void;
  closeDrawer: () => void;
  isOpen: boolean;
}

const DrawerContext = createContext<DrawerContextType | null>(null);

export const DrawerProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [config, setConfig] = useState<DrawerConfig | null>(null);

  const openDrawer = (drawerConfig: DrawerConfig) => {
    setConfig(drawerConfig);
    setIsOpen(true);
  };

  const closeDrawer = () => {
    setIsOpen(false);
    config?.onClose?.();
    // Clear config after a short delay to allow closing animation
    setTimeout(() => setConfig(null), 150);
  };

  const handleDrawerClose = () => {
    closeDrawer();
  };

  return (
    <DrawerContext.Provider value={{ openDrawer, closeDrawer, isOpen }}>
      {children}
      <Drawer anchor={config?.anchor || "right"} open={isOpen} onClose={handleDrawerClose}>
        {config?.content}
      </Drawer>
    </DrawerContext.Provider>
  );
};

/**
 * useDrawer
 *
 * Custom hook to access the DrawerContext.
 * Provides methods to open and close a drawer with dynamic content
 * from anywhere in the application.
 *
 * @returns {DrawerContextType} Drawer context methods (openDrawer, closeDrawer, isOpen)
 */
export const useDrawer = (): DrawerContextType => {
  const context = useContext(DrawerContext);
  if (!context) {
    throw new Error("useDrawer must be used within a DrawerProvider");
  }
  return context;
};
