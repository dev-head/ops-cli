#!/usr/bin/env bash

#-{USER CREATE}-#

USERNAME="${1}"
PUBLIC_SSHKEY="${2}"
HOME_DIR="/home/${USERNAME}"

echo "[starting...][${0}]::[${USERNAME}]::[${HOME_DIR}]::[${PUBLIC_SSHKEY}]"

if [ -z "${USERNAME}" ]; then
    echo "Missing USERNAME as first argument [${USERNAME}]"
    exit 1
fi

if [ -z "${PUBLIC_SSHKEY}" ]; then
    echo "Missing PUBLIC SSHKEY as second argument [${PUBLIC_SSHKEY}]"
    exit 1
fi

# ensure groups
groupadd admin 2> /dev/null | true \
    && groupadd root        2> /dev/null | true \
    && groupadd adm         2> /dev/null | true \
    && groupadd sudo        2> /dev/null | true \
    && groupadd www-data    2> /dev/null | true \
    && groupadd staff       2> /dev/null | true


# safely add user.
useradd --user-group \
    --shell /bin/bash    \
    --home ${HOME_DIR}  \
    --create-home ${USERNAME}  2> /dev/null | true


usermod -G root,adm,sudo,www-data,staff,admin ${USERNAME}

mkdir -p /home/${USERNAME}/.ssh
touch /home/${USERNAME}/.ssh/authorized_keys
echo ${PUBLIC_SSHKEY} > /home/${USERNAME}/.ssh/authorized_keys
chmod 644 /home/${USERNAME}/.ssh/authorized_keys
chmod 755 /home/${USERNAME}/.ssh
chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}