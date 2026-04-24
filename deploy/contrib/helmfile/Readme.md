# Prism install

## Add chart repo and proxy

In our helmfile, we reference chart version pushed to an artifactory. For helmfile to be able to add the artifactory as a repo and pull charts from it, you must be authenticated and give helm the adress of the right proxy.

Proxy to use on Mobility and Alcea VM is `http://internet-france.corp.thales:8080` and should be define in `HTTP_PROXY` and `HTTPS_PROXY` environment variable.

To authentifciate, you must create a token:
- Go at `https://artifactory.thalesdigital.io/ui/repos/tree/General/helm-internal/fred/thalesgroup/fred`
- Click on your avatar in the top right
- Click on "Set me up"
- Choose "Helm" (**NOT** "Helmoci")
- Search for "helm-internal"
- Click on "Generate token"
- => You have your token and a command example on how to add the repo to you local helm install

In powershell, the full command would be:
```
$env:HTTP_PROXY="http://internet-france.corp.thales:8080"
$env:HTTPS_PROXY="http://internet-france.corp.thales:8080"
helm repo add helm-internal https://artifactory.thalesdigital.io/artifactory/api/helm/helm-internal --username <email> --password <token>
```

You can check it works by listing fred chart versions with:
```
helm repo update helm-internal
helm search repo helm-internal/fred --versions --devel
```

To contact the cluster with the proxy set for the helm repo, you will need to add the cluster address to the NO_PROXY env var (to not use the proxy when contacting it).

Retrieve the cluster address with:
```
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
```

It its `https://10.103.8.37:6443`, set a `NO_PROXY` without the protocol or port, like:

```
$env:NO_PROXY=localhost,127.0.0.1,10.103.8.37,.cluster.local
```
