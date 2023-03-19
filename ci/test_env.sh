#!/usr/bin/bash -e

echo "In script ..."

env | base64 > /tmp/env


cat /tmp/env
