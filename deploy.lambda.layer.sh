#!/usr/bin/env bash

##
# @dependencies [awscli, zip, rsync, jq]
#
##
cwd=$(pwd)
layer_name="ops-cli.deploy"
build_dir=".lambda-layers"
uuid=$(uuidgen)
work_dir=${build_dir}/${uuid}
code_dir="${work_dir}/${layer_name}/bin"
AWS_PROFILE=${1:Default}


echo "[code_dir]::[${code_dir}]"
mkdir -p ${code_dir}
rsync -av \
   --exclude "${build_dir}" --exclude "log" \
   --exclude ".git" --exclude "__pycache__" --exclude "documentation" \
   --exclude "data/cache/*" --exclude "data/ec2/*" --exclude "data/ssh-keys/*" --exclude "data/upload/*" \
   . ${code_dir}

cd ${work_dir}; zip -r ${layer_name}.zip ${layer_name}; cd ${cwd}

## upload to lambda
## moves uploaded zip to build dir with matching version number.
aws --profile "${AWS_PROFILE}" lambda publish-layer-version \
    --layer-name ops-cli \
    --compatible-runtimes "python3.7" \
    --zip-file "fileb://${work_dir}/${layer_name}.zip" | jq -r '.Version' | xargs -I {} cp ${work_dir}/${layer_name}.zip ${build_dir}/${layer_name}.version-{}.zip

## finally, lets delete the temporary working dir.
rm -Rf "${work_dir}"