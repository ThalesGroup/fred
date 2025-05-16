#!/usr/bin/env bash

WORK_DIR=$(cd `dirname $0` ; pwd)
DOCKER_IMAGE_LIST="
mirror.gcr.io/postgres
mirror.gcr.io/alpine
mirror.gcr.io/minio/minio
mirror.gcr.io/opensearchproject/opensearch-dashboards
mirror.gcr.io/opensearchproject/opensearch
mirror.gcr.io/keycloak/keycloak
mirror.gcr.io/rancher/k3s
"

cd $WORK_DIR

function usage
{
    echo "Usage: $0 <start|stop|status|info|help>" >&2
    exit 1
}

function log
{
    echo -e "$(date '+%F %T') - $*"
}

function log_ok
{
    log "$* [\e[32mDONE\e[0m]\n"
}

function log_ko
{
    log "$* [\e[31mFAILED\e[0m]\n" >&2
    exit 1
}

function check_requirements
{
    log_msg="Check requirements"
    free_space_kb=$(df --output=avail /var/lib/docker | tail -1)

    log "\e[36m$log_msg\e[0m"

    log "... docker binary"
    type docker > /dev/null || log_ko "$log_msg. Please install docker"

    log "... index.docker.io access"
    docker search alpine --limit 1 > /dev/null || log_ko "$log_msg. Please check proxy setting in /etc/docker/daemon.json"

    log "... docker compose binary"
    docker compose -h > /dev/null || log_ko "$log_msg. Please install docker compose"

    image_number_already_downloaded=$(docker images | grep -E "$(echo $DOCKER_IMAGE_LIST | sed 's# #|#g')" | wc -l)
    if [ $image_number_already_downloaded -eq 7 ]
    then
        # If images are already downloaded, we need 1GB for volumes
        log "... free space on FS /var/lib/docker (1GB required)"
        required_space_kb=$(( 1 * 1024 * 1024 )) # 1GB
        test $free_space_kb -ge $required_space_kb || log_ko "$log_msg. FS /var/lib/docker must have 1GB available"
    else
        # Else, 8GB is required for images + volumes
        log "... free space on FS /var/lib/docker (8GB required)"
        required_space_kb=$(( 8 * 1024 * 1024 )) # 8GB
        test $free_space_kb -ge $required_space_kb || log_ko "$log_msg. FS /var/lib/docker must have 8GB available"
    fi

    log_ok "$log_msg"
}

function set_openai_api_key
{
    [ ! -d ~/.fred ] && mkdir ~/.fred/openai-api-key.env
    grep -q "OPENAI_API_KEY=" ~/.fred/openai-api-key.env 2> /dev/null || echo "OPENAI_API_KEY=$OPENAI_API_KEY" > ~/.fred/openai-api-key.env
}

function build_dev_docker_image
{
    log_msg="Build Fred frontend and backend image for development"
    log "\e[36m$log_msg\e[0m"
    docker compose build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) || log_ko "$log_msg"
    log_ok "$log_msg"
}

function start_docker_containers
{
    log_msg="Start containers"
    log "\e[36m$log_msg\e[0m"
    docker compose up -d || log_ko "$log_msg"
    log_ok "$log_msg"
}

function print_connection_info
{
    cat << EOF

This docker compose stack starts Keycloak, MinIO, Opensearch, and a dummy k8s cluster.
Hereunder, these are the information to connect to each service with their own admin local account.

    - Keycloak:
        url: http://localhost:8080
        user: admin
        password : Azerty123_
        realm: fred

    - MinIO:
        url: http://localhost:9001
        user: admin
        password : Azerty123_
        bucket: fred-dev-content

    - Opensearch:
        url: http://localhost:5601
        user: admin
        password: Azerty123_
        index: localvector

Hereunder these are the nominative SSO accounts registered into the Keycloak realms and their roles:

    - alice (role: admin): Azerty123_
    - bob (roles: editor, viewer): Azerty123_
    - phil (role: viewer): Azerty123_

And these are some useful commands:

    - List the containers : docker ps
    - Restart a container : docker restart <CONTAINER_NAME>
    - Get container logs : docker logs [-f] <CONTAINER_NAME>
    - Attach a tty to a container : docker exec -it <CONTAINER_NAME> sh

    where <CONTAINER_NAME> is in:

    - fred-kube
    - fred-postgres
    - fred-keycloak
    - fred-minio
    - fred-opensearch
    - fred-opensearch-dashboard

EOF
}

# -----------------------------------------------------------------------------
#
# Main
#
# -----------------------------------------------------------------------------

[ $# -ne 1 ] && usage

case "$1" in
    "start")
        check_requirements
        set_openai_api_key
        build_dev_docker_image
        start_docker_containers
        print_connection_info ;;
    "stop")
        docker compose down -v ;;
    "status")
        docker compose ps ;;
    "info")
        print_connection_info ;;
    "help")
        usage ;;
esac