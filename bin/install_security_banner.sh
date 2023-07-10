#!/usr/bin/env bash

echo "[Provisioning with shell script]::[${0}]"

createArchive() {
    if [[ ! -d "${ARCHIVE_DIR}" ]]; then
        echo "[INFO]::[created archive]::[${INSTALL_DIR}]::[${ARCHIVE_DIR}]"
        sudo cp -R "${INSTALL_DIR}" "${ARCHIVE_DIR}"
        echo "created by ${0}" | sudo tee "${ARCHIVE_DIR}/README.md"
    fi
}

MOTD_FILE="99-default-banner"
MOTD_ART_FILE="default.asc"
INSTALL_DIR="/etc/update-motd.d"
FORCE_UPDATE="true"
DATESLUG=$(date +%Y%m%d-%H%I%S)
ARCHIVE_DIR=/tmp/archive.motd-${DATESLUG}

if [[ ! -d "${INSTALL_DIR}" ]]; then
    echo "[ERROR]::[FATAL]::[missing directory]::[${INSTALL_DIR}]"
    exit 1
fi

if [[ ! -f "${MOTD_FILE}" ]]; then
    echo "[ERROR]::[FATAL]::[missing motd file]::[${MOTD_FILE}]"
    exit 1
fi

if [[ ! -f "${MOTD_ART_FILE}" ]]; then
    echo "[ERROR]::[FATAL]::[missing motd art file]::[${MOTD_ART_FILE}]"
    exit 1
fi

if [[ ! -f "${INSTALL_DIR}/${MOTD_ART_FILE}" ]] || [[ "${FORCE_UPDATE}" == "true" ]]; then
    echo "[INFO]::[install motd file]::[${INSTALL_DIR}/${MOTD_FILE}]"
    createArchive
    sudo mv "${MOTD_FILE}" "${INSTALL_DIR}/${MOTD_FILE}"
    sudo chown root:root "${INSTALL_DIR}/${MOTD_FILE}"
fi

if [[ ! -f "${INSTALL_DIR}/${MOTD_ART_FILE}" ]] || [[ "${FORCE_UPDATE}" == "true" ]]; then
    echo "[INFO]::[install motd art file]::[${INSTALL_DIR}/${MOTD_ART_FILE}]"
    createArchive
    sudo mv "${MOTD_ART_FILE}" "${INSTALL_DIR}/${MOTD_ART_FILE}"
    sudo chown root:root "${INSTALL_DIR}/${MOTD_ART_FILE}"
fi

# remove some files to reduce clutter
if [ -f "${INSTALL_DIR}/10-help-text" ]; then sudo rm "${INSTALL_DIR}/10-help-text"; fi
if [ -f "${INSTALL_DIR}/51-cloudguest" ]; then sudo rm "${INSTALL_DIR}/51-cloudguest"; fi

# test
sudo run-parts /etc/update-motd.d/