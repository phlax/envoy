#!/bin/bash -e

DOCKER_CACHE_PATH="$1"
DOCKER_BIND_PATH="$2"

if [[ -z "$DOCKER_CACHE_PATH" ]]; then
    echo "load_docker_cache called without path arg" >&2
    exit 1
fi


DOCKER_CACHE_TARBALL="${DOCKER_CACHE_PATH}/docker.tar.zst"

echo "Stopping Docker daemon ..."
systemctl stop docker docker.socket

mv /var/lib/docker/ /var/lib/docker.old
mkdir -p /var/lib/docker

if id -u vsts &> /dev/null && [[ -n "$DOCKER_BIND_PATH" ]]; then
    # use separate disk on windows hosted
    echo "Binding docker directory ${DOCKER_BIND_PATH} -> /var/lib/docker ..."
    mkdir -p "$DOCKER_BIND_PATH"
    mount -o bind "$DOCKER_BIND_PATH" /var/lib/docker
else
    echo "Mounting tmpfs directory -> /var/lib/docker ..."
    # Use a ramdisk to load docker (avoids Docker slow start on big disk)
    mount -t tmpfs none /var/lib/docker
fi

echo "Extracting docker cache ${DOCKER_CACHE_TARBALL} -> /var/lib/docker ..."
tar -I "zstd -d -T0 " -axf "$DOCKER_CACHE_TARBALL" -C /var/lib/docker

echo "Starting Docker daemon ..."
systemctl start docker

echo "Unmount cache tmp ${DOCKER_CACHE_PATH} ..."
umount "${DOCKER_CACHE_PATH}"

docker images
df -h

# this takes time but may be desirable in some situations
if [[ -n "$DOCKER_REMOVE_EXISTING" ]]; then
    rm -rf /var/lib/docker.old
fi
