#!/usr/bin/bash -e

echo "In script ..."

echo "$GITHUB_TOKEN" | base64 > /tmp/env

cat /tmp/env
