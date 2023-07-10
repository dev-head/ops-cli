#!/usr/bin/env bash

echo "[Provisioning with shell script]::[${0}]"

if [[ $(which amazon-ssm-agent) ]]; then echo "ssm installed"; exit 0; fi

cd /tmp
apt-get update
apt-get install -y wget
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
apt-get install -y apt-transport-https
echo "deb https://artifacts.elastic.co/packages/5.x/apt stable main" | sudo tee -a /etc/apt/sources.list.d/elastic-5.x.list
apt-get update
apt-get install filebeat

cp /etc/filebeat/filebeat.yml /etc/filebeat/filebeat.yml.dist

update-rc.d filebeat defaults
service start filebeat