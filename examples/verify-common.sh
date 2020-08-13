#!/bin/bash -e

NAME="${NAME:-}"
PATHS="${PATHS:-.}"
MANUAL="${MANUAL:-}"
DELAY="${DELAY:-0}"
UPARGS="${UPARGS:-}"


run_log () {
    echo -e "\n> [${NAME}] ${*}"
}

bring_up_example_stack () {
    local args path up_args
    args=("${UPARGS[@]}")
    path="$1"
    read -ra up_args <<< "up --build -d ${args[*]}"

    run_log "Pull the images ($path)"
    docker-compose pull || return 1
    echo
    run_log "Bring up services ($path)"
    docker-compose "${up_args[@]}" || return 1
}

bring_up_example () {
    local paths
    read -ra paths <<< "$(echo "$PATHS" | tr ',' ' ')"
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        bring_up_example_stack "$path" || {
            echo "ERROR: starting ${NAME} ${path}" >&2
            return 1
        }
        popd > /dev/null
    done
    if [[ "$DELAY" -ne "0" ]]; then
        run_log "Snooze for ${DELAY} while ${NAME} gets started"
        sleep "$DELAY"
    fi
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        docker-compose ps
        docker-compose logs
        popd > /dev/null
    done

}

cleanup_stack () {
    local path
    path="$1"
    run_log "Cleanup ($path)"
    docker-compose down
    docker system prune -f
}

cleanup () {
    local paths
    read -ra paths <<< "$(echo "$PATHS" | tr ',' ' ')"
    for path in "${paths[@]}"; do
        pushd "$path" > /dev/null || return 1
        cleanup_stack "$path" || {
            echo "ERROR: cleanup ${NAME} ${path}" >&2
            return 1
        }
        popd > /dev/null
    done
}

_curl () {
    local curl_command
    curl_command=(curl -s)
    if [[ ! "$*" =~ "-X" ]]; then
        curl_command+=(-X GET)
    fi
    for arg in "${@}"; do
        curl_command+=("$arg")
    done
    "${curl_command[@]}" || {
        echo "ERROR: curl (${curl_command[*]})" >&2
        return 1
    }
}

responds_with () {
    local curl_command expected
    expected="$1"
    shift
    _curl "${@}" | grep "$expected" || {
        echo "ERROR: curl expected (${*}): $expected" >&2
        return 1
    }
}

responds_with_header () {
    local expected
    expected="$1"
    shift
    _curl --head "${@}" | grep "$expected"  || {
        echo "ERROR: curl header (${*}): $expected" >&2
        return 1
    }
}

responds_without_header () {
    local curl_command expected
    expected="$1"
    shift
    _curl --head "${@}" | grep "$expected" | [[ "$(wc -l)" -eq 0 ]] || {
        echo "ERROR: curl without header (${*}): $expected" >&2
        return 1
    }
}


trap 'cleanup' EXIT

if [[ -z "$NAME" ]]; then
    echo "ERROR: You must set the '$NAME' variable before sourcing this script" >&2
    exit 1
fi

if [[ -z "$MANUAL" ]]; then
    bring_up_example
fi
