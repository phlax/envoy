#!/bin/bash -e

export NAME=dynamic-config-fs

chmod go+r configs/*
chmod go+rx configs

# shellcheck source=examples/verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Check for response comes from service1 upstream"
responds_with \
    "Request served by service1" \
    http://localhost:10000

run_log "Check config for active clusters pointing to service1"
curl -s http://localhost:19000/config_dump \
    | jq -r '.configs[1].dynamic_active_clusters' \
    | grep '"version_info": "1"'
curl -s http://localhost:19000/config_dump \
    | jq -r '.configs[1].dynamic_active_clusters' \
    | grep '"address": "service1"'

run_log "Set upstream to service2"
sed -i s/service1/service2/ configs/cds.yaml
sed -i s/'version_info: "1"'/'version_info: "2"'/ configs/cds.yaml

run_log "Check for response comes from service2 upstream"
responds_with \
    "Request served by service2" \
    http://localhost:10000

run_log "Check config for active clusters pointing to service2"
curl -s http://localhost:19000/config_dump \
    | jq -r '.configs[1].dynamic_active_clusters' \
    | grep '"address": "service2"'

# curl -s http://localhost:19000/config_dump  \
#    | jq -r '.configs[1].dynamic_active_clusters' \
#    | grep '"version_info": "2"'
