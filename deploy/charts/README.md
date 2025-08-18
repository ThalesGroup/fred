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
docker build -f agentic_backend/dockerfiles/Dockerfile-prod -t ghcr.io/thalesgroup/fred-agent/agentic-backend:0.1 .
docker save ghcr.io/thalesgroup/fred-agent/agentic-backend:0.1 | gzip > /tmp/backend.tgz
sudo k3s ctr images import /tmp/backend.tgz

docker build -f knowledge_flow_backend/dockerfiles/Dockerfile-prod -t ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:0.1 .
docker save ghcr.io/thalesgroup/fred-agent/knowledge-flow-backend:0.1 | gzip > /tmp/knowledge.tgz
sudo k3s ctr images import /tmp/knowledge.tgz

docker build -f frontend/dockerfiles/Dockerfile-prod -t ghcr.io/thalesgroup/fred-agent/frontend:0.1 .
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

## Prepare a kubeconfig file

```
# Do this modification only if the kubeconfig points on the kubernetes cluster hosting the fred backend
cp $HOME/.kube/config /tmp/config
sed -i 's|^\([[:space:]]*server:\)[[:space:]]*.*$|\1 https://kubernetes.default.svc|' /tmp/config
```

# Customize Fred

Overload the file `fred/values.yaml`

```
# Pay attention to the example file
- custom-values-examples/custom-fred.yaml
```

Note :
if `applications.agentic-backend.configuration.storage.*_store.type` OR `applications.knowledge-flow-backend.configuration.storage.*_store.type` are valued with `opensearch`, it will trigger the creation of indexes.

# Deploy Fred

```
cd deploy/charts

helm upgrade -i fred ./fred/ -n dev
OR
helm upgrade -i fred ./fred/ -n dev --values ./fred-custom.yaml
```

## Access

Fred frontend
`http://fred.dev.fred.thalesgroup.com`
login : alice
password: Azerty123_
