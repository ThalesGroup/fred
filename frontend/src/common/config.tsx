/**
 * Interface representing the expected structure of the application configuration.
 * This defines the required backend API URLs and WebSocket URL for the frontend to work properly.
 */
export interface AppConfig {
    backend_url_api: string;          // Base URL of the backend API
    backend_url_knowledge: string;    // Base URL of the knowledge service
    websocket_url: string;            // WebSocket server URL
    feature_flags?: Record<string, boolean>;
    properties?: Record<string, string>;
}

export interface FeatureFlags {
  enableK8Features?: boolean;
}

export const FeatureFlagKey = {
  ENABLE_K8_FEATURES: "enableK8Features",
  ENABLE_ELEC_WARFARE: "enableElecWarfare",
} as const;

export type FeatureFlagKeyType = typeof FeatureFlagKey[keyof typeof FeatureFlagKey];

let config: AppConfig | null = null;

/**
 * Loads the application configuration from /config.json asynchronously.
 * Must be called before the app is rendered.
 */
export const loadConfig = async () => {
    const response = await fetch("/config.json");
    if (!response.ok) {
        throw new Error(`Cannot load config file /config.json: ${response.statusText}`);
    }
    const baseConfig = await response.json();

    // then call backend for dynamic feature flags
    const response_back = await fetch(`${baseConfig.backend_url_api}/fred/config/frontend_settings`);
    const frontendSettings = await response_back.json();
    console.log("Frontend Settings from the backend: ", frontendSettings)
    config = {
      ...baseConfig,
      feature_flags: frontendSettings.feature_flags,
      properties: frontendSettings.properties,
    };
};

/**
 * Returns the loaded configuration.
 * Throws an error if config is not loaded yet.
 */
export const getConfig = (): AppConfig => {
    if (!config) {
        throw new Error("Config file /config.json not loaded yet.");
    }
    return config;
};

/**
 * Checks if a specific feature flag is enabled in the configuration.
 * @param flag 
 * @returns 
 */
export const isFeatureEnabled = (flag: FeatureFlagKeyType): boolean => {
  return !!getConfig().feature_flags?.[flag];
};

export const getProperty = (propertyKey: string): string => {
  return getConfig().properties?.[propertyKey];
};
