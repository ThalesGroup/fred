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

echo $IP_K3S fred-backend.test | sudo tee -a /etc/hosts
echo $IP_K3S fred.test | sudo tee -a /etc/hosts
```
Create a secret containing a kubeconfig file

```
# If the kubeconfig points on a remote kubernetes cluster :
kubectl create secret generic fred-backend-kubeconfig --from-file=$HOME/.kube/config -n test

# If the kubeconfig points on the kubernetes cluster hosting the fred backend
cp $HOME/.kube/config /tmp/config
sed -i 's|^\([[:space:]]*server:\)[[:space:]]*.*$|\1 https://kubernetes.default.svc|' /tmp/config
kubectl create secret generic fred-backend-kubeconfig --from-file=/tmp/config -n test
```

Prepare a custom values file for the backend and the frontend 

```
# Pay attention to the example files
- custom-fred-backend.yaml
- custom-fred-frontend.yaml
```

Deploy backend and frontend

```
cd deploy/charts/
helm upgrade -i fred-backend ./backend/ --values ./custom-fred-backend.yaml -n test
helm upgrade -i fred-frontend ./frontend/ --values ./custom-fred-frontend.yaml -n test
```

Then access to fred 

`http://fred.test`
