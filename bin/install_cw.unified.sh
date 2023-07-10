#!/usr/bin/env bash

# install_cw
# @execute ./install_cw.unified.sh Example Production api-ec2

Platform=${1:Example}
Environment=${2:Production}
Project=${3:ec2}

#-{CLOUD WATCH AGENT INSTALL/CONFIG------------------------------------------------------------------------------------#
CW_DEB_LINK="https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb"
CW_DEB_SIG="https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb.sig"
CW_GPG_PUB="https://s3.amazonaws.com/amazoncloudwatch-agent/assets/amazon-cloudwatch-agent.gpg"
CW_WORK_DIR="/tmp/install_cloudwatch_logs"

function InstallCloudWatchAgent() {
    echo "[$0]::[InstallCloudWatchAgent()]::[started]"
    apt-get install -y curl jq=1.4-2.1~ubuntu14.04.1

    echo "[$0]::[creatingWorkspace()]::[${CW_WORK_DIR}]::[started]"
    mkdir -p "${CW_WORK_DIR}"; cd "${CW_WORK_DIR}"
    echo "[$0]::[creatingWorkspace()]::[completed]"
    #------------------------------------------------------------------------------------------------------------------#

    echo "[$0]::[downloadInstall()]::[started]"
    curl -L "${CW_DEB_LINK}" -O
    curl -L "${CW_DEB_SIG}" -O
    curl -L "${CW_GPG_PUB}" -O
    echo "[$0]::[downloadInstall()]::[completed]"
    #------------------------------------------------------------------------------------------------------------------#

    if [[ -f /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl ]]; then
      echo "[$0]::[deletePreviousInstall()]::[started]"

      echo "cloudwatch agent installed; removing..."
      rm -Rf /opt/aws/amazon-cloudwatch-agent/logs/*

      if [[ -f /opt/aws/amazon-cloudwatch-agent/doc/amazon-cloudwatch-agent-schema.json ]]; then
         rm /opt/aws/amazon-cloudwatch-agent/doc/amazon-cloudwatch-agent-schema.json
      fi

      if [[ -f /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/file_amazon-cloudwatch-agent-schema.json ]]; then
         rm //opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/file_amazon-cloudwatch-agent-schema.json
      fi
      if [[ -d /opt/aws/amazon-cloudwatch-agent/etc ]]; then
        rm -Rf /opt/aws/amazon-cloudwatch-agent/etc
      fi
      apt-get purge amazon-cloudwatch-agent | true
      dpkg -P amazon-cloudwatch-agent
      echo "[$0]::[deletePreviousInstall()]::[completed]"
    fi

    echo "[$0]::[install()]::[started]"
    dpkg -i -E ./amazon-cloudwatch-agent.deb
    echo "[$0]::[install()]::[completed]"

    #------------------------------------------------------------------------------------------------------------------#
    echo "[$0]::[cleanUp()]::[started]"
    if [[ ! -f /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl ]]; then
        echo "[failed to install cloud watch]"
        exit 2
    fi

    if [[ -d "${CW_WORK_DIR}" ]]; then
        echo "[removing workspace]::[${CW_WORK_DIR}]"
        cd /tmp;
        rm -Rf "${CW_WORK_DIR}"
    fi
    echo "[$0]::[cleanUp()]::[completed]"

    echo "[$0]::[InstallCloudWatchAgent()]::[completed]"
}
function WriteCloudWatchMetricConfig() {
    echo "[$0]::[WriteCloudWatchMetricConfig()]::[started]"

  cat > /etc/cloudwatch_metrics.json <<EOL
{
    "namespace": "${Platform}/${Environment}-${Project}",
    "metrics_collected": {
      "cpu": {
        "measurement": [
          {"name": "cpu_usage_active", "rename": "CPU Usage Active", "unit": "Percent"},
          {"name": "cpu_usage_iowait", "rename": "CPU Usage IOWait", "unit": "Percent"}
        ],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": [
          {"name": "used_percent", "rename": "Disk Used %", "unit": "Gigabytes"},
          {"name": "inodes_free", "rename": "Inodes Free", "unit": "Count"}
        ],
        "ignore_file_system_types": [
          "sysfs", "devtmpfs"
        ],
        "metrics_collection_interval": 300
      },
      "diskio": {
        "resources": [
          "*"
        ],
        "measurement": [
          "reads",
          "writes",
          "read_bytes",
          "write_bytes",
          "io_time"
        ],
        "metrics_collection_interval": 300
      },
      "swap": {
        "measurement": [
          {"name": "swap_used_percent", "rename": "Used Swap %"}
        ]
      },
      "mem": {
        "measurement": [
          {"name": "mem_used_percent", "rename": "Used Mem %"}
        ],
        "metrics_collection_interval": 60
      },
      "net": {
        "resources": [
          "*"
        ],
        "measurement": [
          {"name": "bytes_sent", "rename": "Bytes Sent"},
          {"name": "bytes_recv", "rename": "Bytes Rec"},
          {"name": "packets_sent", "rename": "Pkts Sent"},
          {"name": "packets_recv", "rename": "Pkts Rec"},
          {"name": "drop_in", "rename": "Incoming Pkts Dropped"},
          {"name": "drop_out", "rename": "Sent Pkts Dropped"},
          {"name": "err_in", "rename": "Receive Errors"},
          {"name": "err_out", "rename": "Transmit Errors"}
        ]
      },
      "netstat": {
        "measurement": [
          "tcp_established",
          "tcp_syn_sent",
          "tcp_close"
        ],
        "metrics_collection_interval": 300
      },
      "processes": {
        "measurement": [
          "paging",
          "blocked"
        ]
      }
    },
    "append_dimensions": {
      "InstanceId": "\${aws:InstanceId}"
    },
    "aggregation_dimensions" : [["AutoScalingGroupName"], ["InstanceId"], []]
  }
EOL
  echo "[$0]::[WriteCloudWatchMetricConfig()]::[completed]"
}

function WriteCloudWatchLoggingConfig() {
    echo "[$0]::[WriteCloudWatchLoggingConfig()]::[started]"

    cat > /etc/cloudwatch_log_files.json <<EOL
[
  {
      "file_path": "/var/log/syslog",
      "log_group_name": "${Platform}/${Environment}-${Project}",
      "log_stream_name": "syslog",
      "timestamp_format": "%b %d %H:%M:%S",
      "timezone": "Local"
  },
  {
      "file_path": "/var/log/auth.log",
      "log_group_name": "${Platform}/${Environment}-${Project}",
      "log_stream_name": "auth.log",
      "timestamp_format": "%b %d %H:%M:%S",
      "timezone": "Local"
  },
  {
      "file_path": "/var/log/cloud-init-output.log",
      "log_group_name": "${Platform}/${Environment}-${Project}",
      "log_stream_name": "cloud-init-output.log",
      "timestamp_format": "%b %d %H:%M:%S",
      "timezone": "Local"
  },
  {
      "file_path": "/var/log/aws/codedeploy-agent/codedeploy-agent.log",
      "log_group_name": "${Platform}/${Environment}-${Project}",
      "log_stream_name": "codedeploy-agent.log",
      "timestamp_format": "%Y-%m-%d %H:%M:%S",
      "timezone": "Local"
  }
]
EOL
echo "[$0]::[WriteCloudWatchLoggingConfig()]::[completed]"
}

function ConfigureCloudWatchAgent() {
  echo "[$0]::[ConfigureCloudWatchAgent()]::[started]"
  WriteCloudWatchLoggingConfig
  WriteCloudWatchMetricConfig
  DIST_CONFIG=/opt/aws/amazon-cloudwatch-agent/doc/amazon-cloudwatch-agent-schema.json
  /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a stop | true
  cp ${DIST_CONFIG} /tmp/cloudwatch-dist.json

  rm /tmp/cloudwatch-metrics-added.json /tmp/cloudwatch-logs-added.json /tmp/cloudwatch-namespace-added.json | true

  jq --argfile conf /etc/cloudwatch_log_files.json '.logs.logs_collected.files.collect_list = $conf' /tmp/cloudwatch-dist.json > /tmp/cloudwatch-logs-added.json
  jq --argfile conf /etc/cloudwatch_metrics.json '.metrics = $conf' /tmp/cloudwatch-logs-added.json > /tmp/cloudwatch-metrics-added.json
  jq ".metrics.namespace = \"${Platform}/${Environment}-${Project}\" | .logs.log_stream_name = \"${Platform}-${Environment}-${Project}\" | .logs.logs_collected.files.collect_list[].log_group_name = \"${Platform}-${Environment}-${Project}\"" /tmp/cloudwatch-metrics-added.json > /tmp/cloudwatch-namespace-added.json
  cp /tmp/cloudwatch-namespace-added.json ${DIST_CONFIG}

  # Start the agent up with new config | send to background in order to work around super smart script that wants to run it in the forground if unattended.
  /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:${DIST_CONFIG} -s &>/dev/null &

  echo "[$0]::[ConfigureCloudWatchAgent()]::[completed]"
}

#-{Install the AWS CloudWatch Agent}-----------------------------------------------------------------------------------#
echo "[starting for]::[${Platform}]::[${Environment}]::[${Project}]"
InstallCloudWatchAgent
ConfigureCloudWatchAgent
echo "[completed for]::[${Platform}]::[${Environment}]::[${Project}]"
