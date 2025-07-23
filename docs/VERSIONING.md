# Practices of tags

## intro

We follow the versioning ![Semantic Versioning 2.0.0](https://semver.org/).


We currently use this practice
- `main` is the branch containing the reference code and helm charts for binary and deployment
- We follow two tags practice to generate releases
- The version between code and deployment charts are not related to each other

## New code release

Tag the `main` branch with a tag `code/vX.Y.Z`.

It will trigger a workflow that build three packages based on dockerfile `/<package>/Dockerfiles/Dockerfile`.
- `agentic-backend:<version>`
- `knowledge-flow-backend:<version>`
- `frontend:<version>`


## New chart release

Tag the `main` branch with a tag `chart/vA.B.C`.

It will trigger a workflow that build three packages based on dockerfile `/deploy/charts/<package>`.
- `agentic-backend:<version>`
- `knowledge-flow-backend:<version>`
- `frontend:<version>`

## How ?

Currently Helm charts have to be adapted to deploy a specific version of code. We invite maintainers to:
- tag a verified version of the code with `code/version`
- then report the version of the code in the helm charts and adapt helm charts values and templates
- then tag the main branch with `chart/version`

