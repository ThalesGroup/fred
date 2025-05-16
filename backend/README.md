# fred-backend

## Essentials

1. you can start Fred backend using docker or local python environment
2. it will use your local .kube configuration to interact with target Kubernetes clusters.
3. It requires an OPENAI token to perform calls to openai llm.
4. It requires additional configuration and credentials for various  advanced features. But you should be able to run Fred without these.

## Overview

Fred backend (Fred in short) is an API server that exposes a number of REST endpoints that can be used to understand, optimize and monitor a
Kubernetes application
with a focus on maintainability and optimization.
Fred is meant to let you add your own routes, and contribute to the knowledge that will be accumulated and
summarized to ultimately provide you with a very powerful AI assistant that will be aware not only
of the technical details of your K8 Fredapplications, but also about its usage and external environmental or context
information.

As of today, the following REST endpoints are implemented:

- [fred/footprint/carbon](fred/footprint/carbon): to get the carbon consumption estimates of your Kubernetes
  application. It requires some probes to be installed in your K8 application.
- [fred/footprint/energy](fred/footprint/energy): to get energy consumption estimates of your Kubernetes application and
  to get the energy mix.
- [fred/footprint/finops](fred/footprint/finops) : to get the cost of a cloud cluster from its billing APIs. It requires
  access to your hosting cloud Finops APIs.
- [fred/kube](fred/kube) : to get Kubernetes resources information. It requires a .kubeconfig to get in touch with one
  or several K8 clusters.
- [fred/ai](fred/ai) : Fred AI services + REST APIs to manage the AI produced resources. This requires some access to a
  llm providers.
- [fred/ui_service](fred/ui_service) : a few high-level APIs to serve UIs implemented on top of Fred.

## Architecture

Fred is designed to be robust, industrial yet lightweight and developer friendly.
The way it works is to rely on a filesystem (or S3) based cache.
This cache will store the information collected from the various external components
(K8 clusters, openai services, electricity map online service, etc...).

This design has several benefits:

- It is laptop-friendly. It is common to use fred as a local service running on top of a laptop and make it connect
  to your working K8 clusters. The typical fred user is a system administrator in charge of monitoring its K8
  clusters.
- It avoids regenerating costly (llm) data at each request. This is crucial to not recompute the same data over and over
  again.
- It makes right-api very fast.
- It allows offline working.
- It provides an important import / export feature.
- Last, it permits a development mode for developers. Zip simulated data can be exchanged easily among developers to
  develop UIs or additional services.

## Using the Simulation mode

We start by explaining the so-called development mode.
Type in

```sh
make run
```

This launches an empty instance.
It expects a valid OpenAI API key in the `OPENAI_API_KEY` environment variable, and a kubeconfig.

- The OpenAI API key must have access to `gpt-4o` model. See [OpenAI help topic - How can I access GPT-4, GPT-4 Turbo, GPT-4o, and GPT-4o mini?](https://help.openai.com/en/articles/7102672-how-can-i-access-gpt-4-gpt-4-turbo-gpt-4o-and-gpt-4o-mini#:~:text=After%20you%20have%20made%20a%20successful%20payment%20of%20%245%20or%20more%20(usage%20tier%201)%2C%20you%27ll%20be%20able%20to%20access%20the%20GPT%2D4%2C%20GPT%2D4%20Turbo%2C%20GPT%2D4o%20models%20via%20the%20OpenAI%20API.) to get more informations.
- Your kubeconfig can point to any kubernetes cluster including k3d, kind, minikube. A great starting point is to try it out with kooker.

From there, fred will start collecting and generating data and save it under
'~/.fred/fred-backend-cache' (as set in the resource/configuration-dev.yaml file).

If you do not want at all to interact with a remote or development K8 cluster nor perform some openai requests,
get in touch with contributors to get a ready-to-use zip archive that you can simply unzip in '~/.fred/'.
You will then work in offline mode.

## Getting Started

This repository requires:

- `make`
- Docker if you want to run the application in Docker
- Python 3.12.8 for local development

To list all the available commands, run :

```sh
make help
```

### Local Development mode

Simply type in:

```sh
make run
```

That creates a local virtualenv environment.
To start it using Python, type in:

```sh
python src/main.py --server.configurationPath ./config/configuration.yaml --server.baseUrlPath /fred-backend
```

or equivalently

```sh
make run
```

### Ading a new python package

Proceed as follows:

```sh
source .venv/bin/activate
poetry add python-jose@3.3.0
```

### Visual Code

To debug in VisualCode, ask copilot to generate a .vscode/launch.json file. Choose in it the startup configuration you
need.

```json
{
  "configurations": [
    {
      "type": "debugpy",
      "request": "launch",
      "name": "Launch Fred API",
      "program": "${workspaceFolder}/src/main.py",
      "args": [
        "--server.configurationPath",
        "${workspaceFolder}/config/configuration.yaml",
        "--server.baseUrlPath",
        "/fred"
      ]
    }
  ]
}
```

### Logging

You can use the LOG_LEVEL environment variable.

```sh
LOG_LEVEL=DEBUG python -m unittest fred.kube.test_kube_simulation_service
```

### API documentation and tests

The Swagger UI is accessible at `http://<host>:<port>/docs`, typically `http://localhost:8000/fred/docs#/`. Of course; follow the host and port of your configuration file. You will have the documentation of the APIs and buttons to test it (`Try it out`).

## Docker

To run the application in Docker, first build the image:

```sh
make docker-build 
```

This should build a  registry.thalesdigital.io/fred/fred:0.1-dev image. Then

```sh
make docker-run
```

Checkout the `http://localhost:8000/fred/docs#/` url first. You should see the backend swagger UI.
What you will see depends on your local ~/.kube folder. If your local kube configuration points to AWS, GCP or AZURE hosted kubernetes
it is likely you will need extra package to authentify accesses. 

## Fred application manual page

Type in:

```sh
python src/main.py -h
```

```text
usage: main.py [-h] [--server.address SERVER_ADDRESS] [--server.port SERVER_PORT] [--server.baseUrlPath SERVER_BASE_URL_PATH] [--server.configurationPath SERVER_CONFIGURATION_PATH]
               [--server.logLevel SERVER_LOG_LEVEL]

Rift microservice

options:
  -h, --help            show this help message and exit
  --server.address SERVER_ADDRESS
                        Specify the address of the server
  --server.port SERVER_PORT
                        Specify the port of the server
  --server.baseUrlPath SERVER_BASE_URL_PATH
                        Specify the base url for the API entrypoints
  --server.configurationPath SERVER_CONFIGURATION_PATH
                        Specify the path of the configuration used
  --server.logLevel SERVER_LOG_LEVEL
                        Specify the log level of the server
```