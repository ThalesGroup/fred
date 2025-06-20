# Installation

Déployer le frontend et le backend de fred
```
cd backend
docker build -f dockerfiles/Dockerfile-dev -t registry.thalesdigital.io/tsn/innovation/projects/fred/backend:0.1 .
docker save registry.thalesdigital.io/tsn/innovation/projects/fred/backend:0.1 | gzip > /tmp/backend.tgz
sudo k3s ctr images import /tmp/backend.tgz

cd ../frontend
docker build -f dockerfiles/Dockerfile-dev -t registry.thalesdigital.io/tsn/innovation/projects/fred/frontend:0.1 .
docker save registry.thalesdigital.io/tsn/innovation/projects/fred/frontend:0.1 | gzip > /tmp/frontend.tgz
sudo k3s ctr images import /tmp/frontend.tgz


IP_K3S=$(hostname -I | awk '{print $1}')

echo $IP_K3S fred-backend.test | sudo tee -a /etc/hosts
echo $IP_K3S fred.test | sudo tee -a /etc/hosts

PUIS

kubectl create secret generic fred-backend-kubeconfig --from-file=$HOME/.kube/config -n test


helm upgrade -i fred-backend ./backend/ --values ./custom-fred-backend.yaml -n test
helm upgrade -i fred-frontend ./frontend/ --values ./custom-fred-frontend.yaml -n test
```
