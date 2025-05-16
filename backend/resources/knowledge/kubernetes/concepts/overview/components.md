# Kubernetes Components

This page provides a high-level overview of the essential components that make up a Kubernetes cluster.

## Core Components

A Kubernetes cluster consists of a control plane and one or more worker nodes. Here's a brief overview of the main components:

### Control Plane Components

Manage the overall state of the cluster:

kube-apiserver: The core component server that exposes the Kubernetes HTTP API

etcd: Consistent and highly-available key value store for all API server data

kube-scheduler: Looks for Pods not yet bound to a node, and assigns each Pod to a suitable node.

kube-controller-manager: Runs controller to implement Kubernetes API behavior.

cloud-controller-manager: Integrates with underlying cloud provider(s).

### Node Components

Run on every node, maintaining running pods and providing the Kubernetes runtime environment:

kubelet: Ensures that Pods are running, including their containers.

kube-proxy: Maintains network rules on nodes to implement service.

Container runtime: Software responsible for running containers.

Your cluster may require additional software on each node; for example, you might also run [systemd](https://systemd.io/) on a Linux node to supervise local components.

## Addons

Addons extend the functionality of Kubernetes. A few important examples include:

DNS: For cluster-wide DNS resolution

Web UI: For cluster management via a web interface

Container Resource Monitoring: For collecting and storing container metrics

Cluster-level Logging: For saving container logs to a central log store

## Flexibility in Architecture

Kubernetes allows for flexibility in how these components are deployed and managed. The architecture can be adapted to various needs, from small development environments to large-scale production deployments.