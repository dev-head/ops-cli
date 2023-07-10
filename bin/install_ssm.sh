#!/usr/bin/env bash

echo "[Provisioning with shell script]::[${0}]"

if [[ $(which amazon-ssm-agent) || -d "/snap/amazon-ssm-agent" ]]; then
    echo "ssm installed"
else
    mkdir -p /tmp/install_aws_ssm
    cd /tmp/install_aws_ssm
    wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb

    if [[ ! -f "amazon-ssm-agent.deb" ]]; then
        echo "==> ERROR: Failed to download [amazon-ssm-agent.deb]"
        exit 1
    fi

    dpkg -i amazon-ssm-agent.deb

    rm -Rf /tmp/install_aws_ssm
fi