# Installation

## Requirements

- A fully functional Kubernetes cluster (Kubernetes Vanilla, RKE2, K3S, or more dev-oriented alternatives - Kind, K3D, Minikube, etc.)
  - A `dev` namespace (can be created with `kubectl create namespace dev`)
- [Helm binary](https://helm.sh/docs/intro/install/)
- A SQL database engine
- A S3 bucket
- An IDP provider (such as Keycloak or another alternative)
- A full-text search engine (such as Opensearch or another alternative)

## Build images

Build the agentic backend, the knowledge-flow backend, and the frontend images:

### 1. Build the Docker images

```bash
docker build -f agentic-backend/dockerfiles/Dockerfile-prod -t ghcr.io/thalesgroup/fred-agent/agentic-backend:v1.0.0 .
docker build -f knowledge_flow_backend/dockerfiles/Dockerfile-prod -t ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:v1.0.0 .
docker build -f frontend/dockerfiles/Dockerfile-prod -t ghcr.io/thalesgroup/fred-agent/frontend:v1.0.0 .
```

### 2. Load the images into your Kubernetes cluster

Depending on your Kubernetes setup (k3s, k3d, minikube, etc.), injecting images into the local cluster can differ. Make sure to follow the approach that matches your environment. Below, we give detailed instructions for k3s and k3d users.

#### If you use **k3s** (uses containerd, not Docker):

You need to save the images locally and import them into the internal containerd registry used by k3s.

```bash
# Agentic backend
docker save ghcr.io/thalesgroup/fred-agent/agentic-backend:v1.0.0 | gzip > /tmp/agentic-backend.tgz
sudo k3s ctr images import /tmp/agentic-backend.tgz

# Knowledge-flow backend
docker save ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:v1.0.0 | gzip > /tmp/knowledge-flow-backend.tgz
sudo k3s ctr images import /tmp/knowledge-flow-backend.tgz

# Frontend
docker save ghcr.io/thalesgroup/fred-agent/frontend:v1.0.0 | gzip > /tmp/frontend.tgz
sudo k3s ctr images import /tmp/frontend.tgz
```

> **Note:**
> The `k3s ctr images import ...` command is specific to k3s. It imports Docker images into the containerd image registry used internally by k3s clusters.

#### If you use **k3d** (K3S-in-Docker):

You can import your locally built images directly into your k3d cluster using the following commands:

```bash
# Agentic backend
k3d image import ghcr.io/thalesgroup/fred-agent/agentic-backend:v1.0.0 -c <YOUR_K3D_CLUSTER_NAME>

# Knowledge-flow backend
k3d image import ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:v1.0.0 -c <YOUR_K3D_CLUSTER_NAME>

# Frontend
k3d image import ghcr.io/thalesgroup/fred-agent/frontend:v1.0.0 -c <YOUR_K3D_CLUSTER_NAME>
```
Replace `<YOUR_K3D_CLUSTER_NAME>` with the name of your k3d cluster (e.g., `k3d-k3s-default`).

> **Note:**
> The `k3d image import` command copies the image into all the k3d nodes (backed by Docker), making the image available for use in your deployments.

## Prepare hosts file

```
IP_K3S=$(hostname -I | awk '{print $1}')
echo $IP_K3S fred.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
```

## Prepare a kubeconfig file

```
# Do this modification only if the kubeconfig points on the kubernetes cluster hosting the fred backend
cp $HOME/.kube/config /tmp/config
sed -i 's|^\([[:space:]]*server:\)[[:space:]]*.*$|\1 https://kubernetes.default.svc|' /tmp/config
```

> ⚠️ **Warning:** This command will replace the server address for **all clusters** defined in the kubeconfig file.  
> If your kubeconfig contains multiple clusters, this may affect other contexts and is not limited to just the intended one.

If you are fine with the new Kubernetes config file at ``/tmp/config``, you can use it for the rest of the instructions. 

- Either move it to `~/.kube/config`
- Or define the environment variable: `export KUBECONFIG=/tmp/config`

# Customize Fred

Overload the file `fred/values.yaml`

> ⚠️ **Warning:** Pay attention to the example file ``custom-values-examples/custom-fred.yaml``

Note:
if `applications.agentic-backend.configuration.storage.*_store.type` OR `applications.knowledge-flow-backend.configuration.storage.*_store.type` are valued with `opensearch`, it will trigger the creation of indexes.

# Deploy Fred

```
cd deploy/charts

helm upgrade -i fred ./fred/ -n dev
OR
helm upgrade -i fred ./fred/ -n dev --values ./fred-custom.yaml
```

## Access

- URL : [Fred frontend](http://fred.dev.fred.thalesgroup.com)

If you activated the Fred's security feature:
  
  - login : ``alice``
  - password: ``Azerty123_``
