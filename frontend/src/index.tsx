import {Provider} from "react-redux";
import "./styles.css";
import "./index.scss";
import {createRoot} from 'react-dom/client';
import FredUi from "./app/App.tsx";
import {store} from "./common/store.tsx";
import { KeyCloakService } from "./security/KeycloakService.ts";
import { loadConfig } from "./common/config.tsx";

const startApp = async () => {
  console.info("Starting Fred UI...");
  try {
    await loadConfig(); // <-- await config loading FIRST
    console.info("Configuration loaded successfully");
    KeyCloakService.CallLogin(() => {
      createRoot(document.getElementById('root') as HTMLElement)
        .render(
          <Provider store={store}>
            <FredUi/>
          </Provider>
        );
    });
  } catch (error) {
    console.error("Failed to load config:", error);
    // Optionally render a fatal error page
  }
};

startApp(); // <-- Start everything
