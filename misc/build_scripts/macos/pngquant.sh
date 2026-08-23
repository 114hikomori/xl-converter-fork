#!/bin/bash
set -euo pipefail

PNGQUANT_VERSION="3.0.3"

RUN_DIR=$(pwd)
OUTPUT_DIR="${RUN_DIR}/bin/macos"
TEMP_DIR=$(mktemp -d)
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"

source "${SCRIPT_DIR}/_shared.sh"
trap 'cleanup "${TEMP_DIR}"' EXIT

check_env
check_commands \
    curl \
    tar

# Download
cd "${TEMP_DIR}"
curl -L "https://pngquant.org/pngquant.tar.bz2" -o pngquant.tar.bz2
mkdir extracted
tar -xjf pngquant.tar.bz2 -C extracted

# Move
mkdir -p "${OUTPUT_DIR}"
install -m 755 "$(find extracted -type f -name pngquant | head -n1)" "${OUTPUT_DIR}/pngquant"

echo "Binary copied to: ${OUTPUT_DIR}/pngquant"
