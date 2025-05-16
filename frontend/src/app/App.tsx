import React, { useContext } from "react";
import '@fontsource/roboto';
import '@fontsource/roboto/300.css'; // Light
import '@fontsource/roboto/400.css'; // Regular
import '@fontsource/roboto/500.css'; // Medium
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider.tsx";
import { Profile } from "../pages/Profile.tsx";
import { ExplainWorkload } from "../pages/ExplainWorkload.tsx";
import { ThemeProvider } from '@mui/material/styles';
import { PageError } from "../pages/PageError.tsx";
import { Chat } from "../pages/Chat.tsx";
import SideBar from "./SideBar.tsx";
import { ToastProvider } from "../components/ToastProvider.tsx";
import { darkTheme, lightTheme } from "../styles/theme.tsx";
import { FootprintContextProvider } from "./FootprintContextProvider.tsx";
import { ExplainContextProvider } from "./ExplainContextProvider.tsx";
import { ExplainNamespace } from "../pages/ExplainNamespace.tsx";
import { Scores } from "../pages/Scores.tsx";
import { ConfirmationDialogProvider } from "../components/ConfirmationDialogProvider.tsx";
import { ExplainCluster } from "../pages/ExplainCluster.tsx";
import { FactsCluster } from "../pages/FactsCluster.tsx";
import { FactsNamespace } from "../pages/FactsNamespace.tsx";
import { FactsWorkload } from "../pages/FactsWorkload.tsx";
import { ProtectedRoute } from "../components/ProtectedRoute.tsx";
import { DocumentLibrary } from "../pages/DocumentLibrary.tsx";
import { AgentHub } from "../pages/AgentHub.tsx";
import { FeatureFlagKey, isFeatureEnabled } from "../common/config.tsx";
import { Optimize } from "../pages/Optimize.tsx";
import { Geomap } from "../pages/TheaterOfOperations.tsx";

function MainContent({ }) {
  const applicationContext = useContext(ApplicationContext); // Access the ApplicationContext
  const darkMode = applicationContext.darkMode; // Get the dark mode setting from the context
  return (
    <>
      <ThemeProvider theme={darkMode ? darkTheme : lightTheme}>
        {/* Render the SideBar only if it's not the login page */}
        {<SideBar darkMode={darkMode} onThemeChange={applicationContext.toggleDarkMode} />}

        {/* Main content */}
        <Routes>
          {/* Home Route (no clusterName required) */}
          <Route path="/" element={<ProtectedRoute permission={"viewer"} />}>
            <Route path="" element={<FootprintContextProvider><Chat /></FootprintContextProvider>} />
          </Route>

          {isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && (
            <>
              <Route path="/score/:cluster/:namespace/:application" element={<Scores />} />
              <Route path="/facts-workload" element={<FactsWorkload />} />
              <Route path="/facts-cluster" element={<FactsCluster />} />
              <Route path="/facts-namespace" element={<FactsNamespace />} />
              <Route path="/explain-cluster" element={<ExplainCluster />} />
              <Route path="/explain-namespace" element={<ExplainNamespace />} />
              <Route path="/explain-workload" element={<ExplainContextProvider><ExplainWorkload /></ExplainContextProvider>} />
              <Route path="/optimize" element={<ProtectedRoute permission={"viewer"} />}>
                <Route index element={<Optimize />} />
              </Route>
            </>
          )}
          {isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && (
            <>
              <Route path="/geomap" element={<ProtectedRoute permission={"viewer"} />}>
                <Route index element={<Geomap />} />
              </Route>
            </>
          )}

          <Route path="/chat" element={<ProtectedRoute permission={"viewer"} />}>
            <Route index element={<Chat />} />
          </Route>

          <Route path="/profile" element={<ProtectedRoute permission={"viewer"} />}>
            <Route index element={<Profile />} />
          </Route>

          <Route path="/documentLibrary" element={<ProtectedRoute permission={"viewer"} />}>
            <Route index element={<DocumentLibrary />} />
          </Route>


          <Route path="/agentHub" element={<ProtectedRoute permission={"viewer"} />}>
            <Route index element={<AgentHub />} />
          </Route>

          {/* Redirect for invalid paths */}
          <Route path="*" element={<PageError />} />
        </Routes>
      </ThemeProvider>
    </>
  );
}

function FredUi() {
  return (
    <React.Suspense fallback={<div>Loading</div>}>
      <ToastProvider>
        <ConfirmationDialogProvider>
          <Router>
            <ApplicationContextProvider>
              <MainContent />
            </ApplicationContextProvider>
          </Router>
        </ConfirmationDialogProvider>
      </ToastProvider>
    </React.Suspense>
  );
}

export default FredUi;
