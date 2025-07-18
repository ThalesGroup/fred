# Installation of Fred

## Dependency

- A fully functional Kubernetes cluster
- [Install helm](https://helm.sh/docs/intro/install/)
- An SQL database engine
- A S3 bucket
- An IDP provider (such as keycloak or alternative)
- A full-text search engine (such as opensearch or alternative)

## Build images

Build the agentic backend, the knowledge-flow backend and the frontend images :

```
docker build -f agentic_backend/dockerfiles/Dockerfile -t ghcr.io/thalesgroup/fred-agent/agentic-backend:0.1 .
docker save ghcr.io/thalesgroup/fred-agent/agentic-backend:0.1 | gzip > /tmp/backend.tgz
sudo k3s ctr images import /tmp/backend.tgz

docker build -f knowledge_flow_backend/dockerfiles/Dockerfile -t ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:0.1 .
docker save ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:0.1 | gzip > /tmp/knowledge.tgz
sudo k3s ctr images import /tmp/knowledge.tgz

docker build -f frontend/dockerfiles/Dockerfile -t ghcr.io/thalesgroup/fred-agent/frontend:0.1 .
docker save ghcr.io/thalesgroup/fred-agent/frontend:0.1 | gzip > /tmp/frontend.tgz
sudo k3s ctr images import /tmp/frontend.tgz

```

## Prepare hosts file

```
IP_K3S=$(hostname -I | awk '{print $1}')

echo $IP_K3S agentic-backend.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
echo $IP_K3S fred.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
echo $IP_K3S knowledge-flow-backend.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
```

## Install Knowledge-Flow

Overload the file `knowlegde-flow-backend/values.yaml`, specially the three following variables, we recommend a separated *knowledge-flow-custom.yaml* file

```
env:*
ingress.hosts:*
configuration:*
dotenv:*
kubeconfig:*
```

Then deploy knowledge-flow-backend

```
cd deploy/charts

helm upgrade -i knowledge-flow-backend ./knowledge-flow-backend/ -n dev
OR
helm upgrade -i knowledge-flow-backend ./knowledge-flow-backend/ -n dev --values ./knowledge-flow-custom.yaml
```

## Prepare a kubeconfig file

```
# Do this modification only if the kubeconfig points on the kubernetes cluster hosting the fred backend
cp $HOME/.kube/config /tmp/config
sed -i 's|^\([[:space:]]*server:\)[[:space:]]*.*$|\1 https://kubernetes.default.svc|' /tmp/config
```

## Install the agentic backend

Overload the following variables in `charts/agentic-backend/values.yaml`, we recommend a separated *agentic-backend-custom.yaml* values file :
```
dotenv:*
env:*
kubeconfig:*
```

```
# Pay attention to the example file
- custom-values-examples/agentic-backend-custom.yaml
```

Then deploy the backend :

```
cd deploy/charts/
helm upgrade -i agentic-backend ./agentic-backend/ --values ./custom-values-examples/agentic-backend-custom.yaml -n dev
```

## Install the Fred frontend

Overload the Fred frontend similarly to the following example :

```
# Pay attention to the example file
- custom-values-examples/fred-frontend-custom.yaml
```

Deploy the frontend

```
cd deploy/charts/
helm upgrade -i fred-frontend ./frontend/ --values ./fred-frontend-custom.yaml -n dev
```

## Access

Fred frontend
`http://fred.dev.fred.thalesgroup.com`
login : alice
password: Azerty123_
