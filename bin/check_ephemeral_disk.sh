#!/usr/bin/env bash


INSTANCE_ID=$(curl -Ss http://169.254.169.254/latest/meta-data/instance-id)
INSTANCE_TYPE=$(curl -Ss http://169.254.169.254/latest/meta-data/instance-type)

echo "Hostname          : `uname -n`"
echo "Instance Type     :  $INSTANCE_TYPE"
echo "Instance ID       : $INSTANCE_ID"

OSDEVICE=$(sudo lsblk -o NAME -n | grep -v '[[:digit:]]' | sed "s/^sd/xvd/g")
BDMURL="http://169.254.169.254/latest/meta-data/block-device-mapping/"

for bd in $(curl -s ${BDMURL}); do MAPDEVICE=$(curl -s ${BDMURL}/${bd}/ | sed "s/^sd/xvd/g"); if grep -wq ${MAPDEVICE} <<< "${OSDEVICE}"; then echo "${bd} is ${MAPDEVICE}"; fi; done | grep ephemeral