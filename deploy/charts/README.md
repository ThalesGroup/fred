# Installation of Fred

## Dependency

- A fully functional Kubernetes cluster ( [k3s](https://docs.k3s.io/installation) )
- [Deployment factory installed](https://github.com/ThalesGroup/fred-deployment-factory/tree/main/charts)

## Build images

Build backend and frontend images :

```
cd agentic_backend
docker build -f dockerfiles/Dockerfile-dev -t registry.thalesdigital.io/tsn/innovation/projects/fred/backend:0.1 .
docker save registry.thalesdigital.io/tsn/innovation/projects/fred/backend:0.1 | gzip > /tmp/backend.tgz
sudo k3s ctr images import /tmp/backend.tgz

cd ../frontend
docker build -f dockerfiles/Dockerfile-dev -t registry.thalesdigital.io/tsn/innovation/projects/fred/frontend:0.1 .
docker save registry.thalesdigital.io/tsn/innovation/projects/fred/frontend:0.1 | gzip > /tmp/frontend.tgz
sudo k3s ctr images import /tmp/frontend.tgz

cd ../knowledge-flow
docker build -t dockerfiles/Dockerfile-dev -t registry.thalesdigital.io/tsn/innovation/projects/knowledge_flow_app:0.1 .
docker save registry.thalesdigital.io/tsn/innovation/projects/knowledge_flow_app:0.1 | gzip > /tmp/knowledge.tgz
sudo k3s ctr images import /tmp/knowledge.tgz

```

## Prepare hosts file

```
IP_K3S=$(hostname -I | awk '{print $1}')

echo $IP_K3S fred-backend.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
echo $IP_K3S fred.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
echo $IP_K3S knowledge-flow-backend.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
```

## Install Knowledge-Flow

Overload the file `knowlegde-flow-backend/values.yaml`, specially the three following variables, we recommend a separated *customvalues.yaml* file

```
env:*
ingress.hosts:*
configuration:*
dotenv:*
kubeconfig:*
```

Then deploy knowledge-flow-backend

```
helm upgrade -i knowledge-flow-backend ./knowledge-flow-backend/ -n test
OR
helm upgrade -i knowledge-flow-backend ./knowledge-flow-backend/ -n test --values ./knowledge-flow-backend-custom-values.yaml
```

## Prepare a kubeconfig file

```
# Do this modification only if the kubeconfig points on the kubernetes cluster hosting the fred backend
cp $HOME/.kube/config /tmp/config
sed -i 's|^\([[:space:]]*server:\)[[:space:]]*.*$|\1 https://kubernetes.default.svc|' /tmp/config
```

## Install the Fred backend

Overload the following variables in `charts/backend/values.yaml`, we recommend a separated *backend-customvalues.yaml* file :
```
dotenv:*
env:*
kubeconfig:*
```

```
# Pay attention to the example file
- custom-values-examples/custom-fred-backend.yaml
```

Then deploy the backend :

```
cd deploy/charts/
helm upgrade -i fred-backend ./backend/ --values ./custom-fred-backend.yaml -n dev
```

## Install the Fred frontend

Overload the Fred frontend similarly to the following example :

```
# Pay attention to the example file
- custom-values-examples/custom-fred-frontend.yaml
```

Deploy the frontend

```
cd deploy/charts/
helm upgrade -i fred-frontend ./frontend/ --values ./custom-fred-frontend.yaml -n dev
```

## Access

Fred frontend
`http://fred.dev.fred.thalesgroup.com`
login : alice
password: Azerty123_