#!/bin/bash

check_docker_compose() {
    set -e

    dc_file=${1:-"./docker-compose.yml"}

    if [[ ! -f "${dc_file}" ]]; then
        echo "::error:: Ошибка - нет файла docker-compose.yml"
        exit 1
    fi

    db_service=`yq '.services.db' ${dc_file}`
    if [[ "${db_service}" == "null" ]]; then
        echo "::error:: Ошибка - нет явно заданного сервиса для СУБД (с названием db)"
        exit 1
    fi
}

build_docker_compose() {
    dc_file=${1:-"./docker-compose.yml"}
    docker compose -f "${dc_file}" build --no-cache
}

run_docker_compose() {
    dc_file=${1:-"./docker-compose.yml"}
    docker compose -f "${dc_file}" up -d
}

check_tag() {
    TAG="0.5"
    if [ $(git tag -l "${TAG}") ]; then
        echo "::notice::Тег ${TAG} найден"
    else
        echo "::error::Тег ${TAG} не найден"
        exit 1
    fi
}

ACTION=${1}
DC_PATH=${2:-"./docker-compose.yml"}

case $ACTION in
    "check-compose")
        check_docker_compose "${DC_PATH}"
        ;;
    "build")
        build_docker_compose "${DC_PATH}"
        ;;
    "run")
        run_docker_compose "${DC_PATH}"
        ;;
    "check-tag")
        check_tag
        ;;
        #для ручного запуска
    "all")
        check_docker_compose "${DC_PATH}"
        build_docker_compose "${DC_PATH}"
        run_docker_compose "${DC_PATH}"
        check_tag
        ;;
esac
