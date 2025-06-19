# Fred

Fred is a multi-agent AI assistant to help managing your Kubernetes applications. 
It consists of a python backend, exposing (FastAPI) REST endpoints, and a companion UI that
provides you with a simple but effective chatbot UI.

Fred is primarly a laboratory to explore how to best design a complete multi-agent application using
LangChain and LanGraph. It does not pretend to be a framework, instead it is a complete example
that illustrates how to turn several specialized agents into a fully-fledge expert team ready to assist you in
answering very precise questions about your K8S applications.

Checkout [Fred website](https://fredk8.dev) for details and position papers.

## Installation

Have a look first at [fred website get started](https://fredk8.dev/docs/guides/getting-started/). 

Simply explained, you need to first start the Python backend as explained [here](./backend/README.md),
then the UI as explained [here](./ui/README.md).

Here is the quick procedure for impatient people.

In case you want to use OpenAI models, you will need a valid OpenAI API Key with an access to the *gpt-4o* model - check the [OpenAI help topic - How can I access GPT-4, GPT-4 Turbo, GPT-4o, and GPT-4o mini](https://help.openai.com/en/articles/7102672-how-can-i-access-gpt-4-gpt-4-turbo-gpt-4o-and-gpt-4o-mini#h_f472fd7cbc) to get one.

### Using non containerized development environment

#### 0. Overview

You setup everything directly on your machine in bare-metal.

#### 1. Requirements and installation

The backends requires Python ``3.12.8``. We **strongly** encourage you to use [pyenv](https://github.com/pyenv/pyenv) to install Python.

```
pyenv install 3.12.8
pyenv global 3.12.8

pyenv versions
  system
* 3.12.8 (set by /home/<user>/.pyenv/version)
```

A ``backend/.python-version`` file is part of the repository to ensure your local development environment match fred requirements.
Note that pyenv takes care of both Python and pip, but not poetry. Poetry 1.7 is required. It will be part of the constructed virtual env. Please use the ``make`` command to build it.

```
cd backend/
make build
```

The front end requires node `v22.13.0`.
We **strongly** encourage you to use `nvm` (Installation instructions [here](https://github.com/nvm-sh/nvm?tab=readme-ov-file#install--update-script)) to install and manage node.
Similarly use the `make` command.

```
cd frontend
make build
```

Then use NVM to install the expected release of nodeJS
```
nvm install 22.13.0
```

#### 2. Connection 

In one terminal:

```sh
export OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
cd backend
make run
```

In another terminal:

```sh
cd frontend
make run
```

Then open [https://localhost:5173](https://localhost:5173) in your local browser.

### Using Docker development environment

Watchout: **this is WIP.** The docker compose makes easier to develop the frontend and the backend, deploying and configuring the following required compoments for you:


#### 0. Overview

You setup everything on Docker. Provided Dockerfiles correctly deal with all requirements issues as well leveraging the same Makefiles.

- Keycloak
- Opensearch and Opensearch Dashboards
- MinIO
- a dummy Kubernetes cluster

This guarantees we all share the same environment and Docker images.

#### 1. Requirement

According to the distribution of your docker underlying host, install the following packages:
- Docker, [Install Docker Engine](https://docs.docker.com/engine/install/)
- docker-compose, [Overview of installing Docker Compose](https://docs.docker.com/compose/install/)
- a properly configured kube config file available at ``~/.kube/config`` , for a dev k8s cluster or a Minikube (Installation instructions for Minikube [here](https://kubernetes.io/fr/docs/tasks/tools/install-minikube/))

#### 2. Prepare your Linux docker host

##### 2.1. Proxy environment variables

If you use a proxy to access to the internet, make sure your workstation won't use it to access to the local or container networks.

```sh
export PROXY_URL="<PROXY_URL>"
```
```sh
export https_proxy=$PROXY_URL
export http_proxy=$PROXY_URL
export ftp_proxy=$PROXY_URL
export no_proxy=localhost,127.0.0.1,10.0.0.0/8,172.0.0.0/8,192.168.0.0/16,0.0.0.0,$(hostname -i),$(hostname -s),$(hostname -f | tr '[[:upper:]]' '[[:lower:]]')
```

Tips: You can set the lines above into your ~/.bashrc file to set these environment variables when you log in.

You also need to configure the docker daemon to use the proxy.
```sh
cat << EOF | sudo tee /etc/docker/daemon.json
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "proxies": {
    "http-proxy": "$PROXY_URL",
    "https-proxy": "$PROXY_URL"
  }
}
EOF
```

Restart the docker daemon to apply the previous change.
```sh
sudo systemctl restart docker
```

##### 2.2. Kernel tunning for opensearch container

Increase the vm.max_map_count - this is a requirement for opensearch.
```sh
echo "vm.max_map_count=262144" | sudo tee /etc/sysctl.d/10-opensearch.conf
sudo sysctl -p
```

##### 2.3. Local network name resolution

Add the entry `127.0.0.1 fred-keycloak` into your docker host `/etc/hosts` to be correctly redirected from your web browser.
```sh
grep -q '127.0.0.1.*fred-keycloak' /etc/hosts || echo "127.0.0.1 fred-keycloak" | sudo tee -a /etc/hosts
```

Ensure that following commands work

```
ping fred-keycloak
getent hosts fred-keycloak
```

##### 2.4. Define OpenAI API Key environment variable

Set your OpenAI API Key into the environment variables file `~/.fred/openai-api-key.env` that will be used by the backend container.

```sh
mkdir ~/.fred
echo "OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>" > ~/.fred/openai-api-key.env
```

(as a reminder, go back to [Get Started](#get-started) to get the link to get an OpenAI API Key)


#### 3. Start the stack

Once your docker host is ready, you can start the docker compose stack. The way to start all containers depends on your IDE. VSCode has a plugin called `Dev Containers` that allow to develop directly into the container. But if you do not use VSCode, we provide a script to start the stack.

You are going to use:

- [VSCode IDE](#dev-with-vscode)
- [Another IDE](#dev-without-vscode)

The full environment might take 10-15 minutes to be ready.

<a id="dev-with-vscode"></a>
##### 3.1. Development with VSCode

Open VSCode and make sure `Dev Containers` plugin is installed.

Then in VSCode:
- Press the `F1` key
- Select `Dev Containers: Reopen in Container` (or `Dev Containers: Rebuild and Reopen in Container`)
- Wait until all containers are up and running, and the VSCode extensions are installed in the dev container
- Open the **Run and Debug panel** on the left (shortcut: `Ctrl` + `Shift` + `D`)
- Select **Run Backend**, click the **Play** button, and wait for the process to start. It should be listening on port `8000`
- Do the same for **Run Frontend**, and wait until Vite has started and is listening on port `5173`

<a id="dev-without-vscode"></a>
##### 3.2. Development with another IDE than VSCode

Start all containers with this command:
```sh
chmod u+x ./deploy/docker-compose/fred-compose.sh
./deploy/docker-compose/fred-compose.sh start
```

If you make changes on frontend code, it will be applied without restarting the container.

If you make changes on backend code, you will have to restart the container to apply your changes. Restart it with this command:
```sh
docker restart fred-backend
```

#### 4. Access the web interfaces for dependencies

Some default users are already available and they can connect to fred, opensearch-dashboards and minio:

- Administrator user : `alice`
- Editor user : `bob`
- Viewer user : `phil`

Hereunder the configuration of the following components required by fred:

- Keycloak:
    - URL: http://localhost:8080
    - Admin service account: `admin`

- Opensearch:
    - URL: http://localhost:5601
    - Indice: `localvector`
    - Admin service account: `admin`
    - Read only service account: `fred_ro`
    - Read write service account: `fred_rw`

- MinIO:
    - API URL: http://localhost:9000
    - WebUI URL: http://localhost:9001
    - Bucket: `fred-dev-content`
    - Admin service account: `admin`
    - Read only service account: `fred_ro`
    - Read write service account: `fred_rw`

All passwords are `Azerty123_` for this ephemeral and local development stack.

#### 5. Deploy Fred backend and frontend

```
cd backend
make docker-build
make docker-run

cd ../frontend
make docker-build
make docker-run 
```

## Documentation
-
Documentation is available at [https://fredk8.dev](https://fredk8.dev).

## Contributing

If you are interested in contributing to the project, start by reading the [Contributing guide](/CONTRIBUTING.md).

## License

Fred is apache V2. Checkout the [LICENSE](./LICENSE) for details

## Contacts

- email:dimitri.tombroff.e@thalesdigital.io
- email:fabien.le-solliec@thalesgroup.com
- email:dorian.finel-bache.e@thalesdigital.io
- email:tanguy.jouannic@gmail.com
- email:lorenzo.gerardi@gmail.com
- email:reyyan.tekin@thalesgroup.com
