#!/usr/bin/env bash

set -o pipefail  # trace ERR through pipes
set -o errtrace  # trace ERR through 'time command' and other functions
set -o nounset   ## set -u : exit the script if you try to use an uninitialised variable
set -o errexit   ## set -e : exit the script if any statement returns a non-true return value

trap 'catch_error $? $LINENO' EXIT

# variables that should be passed as arguments.
script_name="${0:-build-lambda-layer}"
layer_name="${1:-ops-cli.deploy}"

# get into that pathing life
cwd=$(pwd)
script_path="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
project_dir="${script_path}/../.."
layers_dir="${project_dir}/lambda/layers"
build_dir="${layers_dir}/build"
archive_dir="${layers_dir}/archive"
deploy_dir="${layers_dir}/deploy"
uuid=$(uuidgen)
work_dir=${build_dir}/${uuid}
code_dir="${work_dir}/${layer_name}/bin"

#----{Script functions}-------------------------------------------------------#
debug() {
  echo "+++++{DEBUG}++++++++++++++++++++++++++++++++++++++++"
  echo "[script_name]::[${cwd}]"
  echo "[script_name]::[${script_name}]"
  echo "[layer_name]::[${layer_name}]"
  echo "[script_path]::[${script_path}]"
  echo "[project_dir]::[${project_dir}]"
  echo "[layers_dir]::[${layers_dir}]"
  echo "[build_dir]::[${build_dir}]"
  echo "[archive_dir]::[${archive_dir}]"
  echo "[deploy_dir]::[${deploy_dir}]"
  echo "[uuid]::[${uuid}]"
  echo "[work_dir]::[${work_dir}]"
  echo "[code_dir]::[${code_dir}]"
  echo "++++++++++++++++++++++++++++++++++++++++++++++++++++"
}

cleanup() {
  if [ -d "${work_dir}" ]; then
    echo "[deleting]::[code_dir]::[${work_dir}]"
    rm -R "${work_dir}"
  fi
}

catch_error() {
  if [ "$1" != "0" ]; then
    echo "!!!!!!!!{ERROR}!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    debug
    cleanup
  fi
}

#----{User functions}---------------------------------------------------------#
test_dependencies(){
  echo "[testing my dependencies]::[zip, rsync]"
  if ! command -v zip &> /dev/null; then
      echo "[ERROR]::[missing required dependencies]::[zip]"
      exit 1
  fi

  if ! command -v rsync &> /dev/null; then
      echo "[ERROR]::[missing required dependencies]::[rsync]"
      exit 1
  fi
}

create_build_dir() {
  echo "[creating]::[code_dir]::[${code_dir}]"

  if [ -d "${code_dir}" ]; then
    echo "[ERROR]::[code_dir exists]::[${code_dir}]"
    exit 1
  fi

  mkdir -p "${code_dir}"
}

copy_source(){
  echo "[copying source code for layer artifact]::["${project_dir}"]::[to]::["${code_dir}"]"

  # check for lambda cli
  # @todo adjust this once conslidation todo is implemented.
  if [ ! -f "${project_dir}/cli.lambda.py" ]; then
    echo "[ERROR]::[expected code base is missing]::[${project_dir}/cli.lambda.py]"
    exit 1
  fi

  if [ ! -d "${code_dir}" ]; then
    echo "[ERROR]::[code_dir does not exists]::[${code_dir}]"
    exit 1
  fi

  # @todo
  #   * provide user ability to define these ignores.
  #   * git ignore might work, specific custom file might be needed though for the filters.
  #   * we should leverage secrets for creds.
  rsync -a \
     --exclude "${build_dir}" --exclude "log" --exclude "terraform" --exclude "lambda" \
     --exclude ".git" --exclude "__pycache__" --exclude "documentation" --exclude ".lambda-layers" \
     --exclude "data/cache/*" --exclude "data/ec2/*" --exclude "data/ssh-keys/*" --exclude "data/upload/*" \
     "${project_dir}" "${code_dir}"
}

create_artifact(){
  echo "[creating zip artifact from copied source]::[${work_dir}]::[to]::[${work_dir}/${layer_name}.zip]"

  if [ ! -d "${code_dir}" ]; then
    echo "[ERROR]::[code_dir does not exists]::[${code_dir}]"
    exit 1
  fi

  cd ${work_dir};
  zip --quiet -r ${layer_name}.zip ${layer_name}
  cd ${cwd}
}

package_archive(){
  if [ ! -f "${work_dir}/${layer_name}.zip" ]; then
    echo "[ERROR]::[missing artifact]::[${work_dir}/${layer_name}.zip]"
    exit 1
  fi

  if [ -f "${deploy_dir}/${layer_name}.zip" ]; then
    echo "[moving previous artifact]::[${deploy_dir}/${layer_name}.zip]::[to]::[${archive_dir}/${layer_name}.${uuid}.zip]"
    mv ${deploy_dir}/${layer_name}.zip ${archive_dir}/${layer_name}.${uuid}.zip
  fi

  echo "[packaging new artifact from]::[${work_dir}/${layer_name}.zip]::[to]::[${deploy_dir}/${layer_name}.zip]"
  mv ${work_dir}/${layer_name}.zip ${deploy_dir}/${layer_name}.zip
}

initialize(){
  test_dependencies
  create_build_dir
  copy_source
  create_artifact
  package_archive
}

#----{Execute}----------------------------------------------------------------#
initialize

#----{Final cleanup}----------------------------------------------------------#
trap cleanup EXIT
