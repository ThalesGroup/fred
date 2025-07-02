# Installation of Fred

## Depedency

- A fully functional Kubernetes cluster ( [k3s](https://docs.k3s.io/installation) )
- [Deployment factory installed](https://github.com/ThalesGroup/fred-deployment-factory/tree/main/charts)
- [Knowlegde-flow backend installed](https://github.com/ThalesGroup/knowledge-flow/tree/main/deploy/charts)

## Build images

Build backend and frontend images :

```
cd backend
docker build -f dockerfiles/Dockerfile-dev -t registry.thalesdigital.io/tsn/innovation/projects/fred/backend:0.1 .
docker save registry.thalesdigital.io/tsn/innovation/projects/fred/backend:0.1 | gzip > /tmp/backend.tgz
sudo k3s ctr images import /tmp/backend.tgz

cd ../frontend
docker build -f dockerfiles/Dockerfile-dev -t registry.thalesdigital.io/tsn/innovation/projects/fred/frontend:0.1 .
docker save registry.thalesdigital.io/tsn/innovation/projects/fred/frontend:0.1 | gzip > /tmp/frontend.tgz
sudo k3s ctr images import /tmp/frontend.tgz
```

## Prepare hosts file

```
IP_K3S=$(hostname -I | awk '{print $1}')

echo $IP_K3S fred-backend.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
echo $IP_K3S fred.dev.fred.thalesgroup.com | sudo tee -a /etc/hosts
```
Prepare a kubeconfig file

```
# Do this modification only if the kubeconfig points on the kubernetes cluster hosting the fred backend
cp $HOME/.kube/config /tmp/config
sed -i 's|^\([[:space:]]*server:\)[[:space:]]*.*$|\1 https://kubernetes.default.svc|' /tmp/config
```

Overload the following variables in `charts/backend/values.yaml`: 
```
dotenv:*
env:*
kubeconfig:*
```

```
# Pay attention to the example files
- examples/custom-fred-backend.yaml
- examples/custom-fred-frontend.yaml
```

Deploy backend and frontend

```
cd deploy/charts/
helm upgrade -i fred-backend ./backend/ --values ./custom-fred-backend.yaml -n dev
helm upgrade -i fred-frontend ./frontend/ --values ./custom-fred-frontend.yaml -n dev
```

Then access to fred 

`http://fred.dev.fred.thalesgroup.com`
