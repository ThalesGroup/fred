# Deployment Configuration

This directory contains Docker Compose files and supporting configuration used for **local development and testing only**.

## Certificate Notice

The certificates located under this folder and sub folders
are **self-signed and non-sensitive**. They are used **only to enable TLS communication** between containers (e.g., OpenSearch and dashboards) in local environments.

- These certificates are:
  - Auto-generated or manually created for test purposes.
  - Not valid for production use.
  - Not associated with any real domains or private credentials.

## Reminder

These files are included to support development workflows such as:

- Running OpenSearch with HTTPS in Docker Compose
- Avoiding mixed-content issues when using local dashboards
- Enabling local testing of TLS scenarios

Do **not** reuse these certificates or keys in production. For real deployments, proper certificate management and secret handling must be enforced.

## 🌐 Runtime Configuration for the Frontend

This frontend uses [Vite](https://vitejs.dev/), which normally injects environment variables (like `VITE_USE_AUTH`) at **build time**. To support dynamic configuration at **runtime** (e.g., when deploying with Helm), we load a runtime config file: `env.js`.

### ✅ Overview

- Runtime config is provided via `/env.js`, mounted as a ConfigMap.
- The frontend reads from `window.__ENV__` instead of `import.meta.env`.
- This enables you to deploy the same Docker image in different environments without rebuilding.

---

### 🔧 How it works

1. **Replace all `import.meta.env.*` usages** with `window.__ENV__`:
   ```ts
   const USE_AUTH = window.__ENV__?.VITE_USE_AUTH === "true";
   ```

2. **Add `/public/env.js` with a default fallback** (for local dev):
   ```js
   window.__ENV__ = {
     VITE_USE_AUTH: "false"
   };
   ```

3. **In `index.html`, include `env.js` before your app code**:
   ```html
   <script>window.__ENV__ = {};</script>
   <script src="/env.js"></script>
   <script type="module" src="/src/main.tsx"></script>
   ```

---

### 📦 Dockerfile (runtime stage)

Ensure `env.js` is created and owned by nginx so it can be overridden at runtime:

```Dockerfile
# In the runtime stage
RUN touch /usr/share/nginx/html/env.js && \
    chown nginx:nginx /usr/share/nginx/html/env.js
```

---

### 🛠️ Helm: Mount runtime config via ConfigMap

In your `values.yaml`:

```yaml
oidc:
  enabled: true

envConfig:
  VITE_USE_AUTH: "true"
```

Define the corresponding `ConfigMap`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Chart.Name }}-env-config
data:
  env.js: |
    window.__ENV__ = {
      VITE_USE_AUTH: "{{ .Values.envConfig.VITE_USE_AUTH }}"
    };
```

Mount it in your `Deployment.yaml`:

```yaml
volumeMounts:
  - name: {{ .Chart.Name }}-env-vol
    mountPath: /usr/share/nginx/html/env.js
    subPath: env.js

volumes:
  - name: {{ .Chart.Name }}-env-vol
    configMap:
      name: {{ .Chart.Name }}-env-config
```

---

### ✅ Result

- ✅ Single Docker image works across all environments
- 🔄 Runtime behavior (like auth, endpoints, feature flags) is configurable
- 🧪 Great for dev, test, staging, and production parity

This setup ensures flexibility, maintainability, and full environment separation — without requiring frontend rebuilds per deployment.

## Contact

For any security or deployment-related concerns, please reach out via the [Fred GitHub repository](https://github.com/ThalesGroup/fred).
