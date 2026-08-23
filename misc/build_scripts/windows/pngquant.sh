#!/bin/bash

PNGQUANT_VERSION="3.0.3"

RUN_DIR=$(pwd)
OUTPUT_DIR="${RUN_DIR}/bin/win/pngquant"
TEMP_DIR=$(mktemp -d)
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"

source "${SCRIPT_DIR}/_shared.sh"

trap 'cleanup "${TEMP_DIR}"' EXIT
set -euo pipefail
check_msys2
check_commands 7z wget

# Download
cd "$TEMP_DIR"
wget "https://pngquant.org/pngquant-windows.zip" -O pngquant.zip
7z x pngquant.zip

# Move
mkdir -p "$OUTPUT_DIR"
mv "${TEMP_DIR}/pngquant/pngquant.exe" "${OUTPUT_DIR}"

echo "Binary copied to: ${OUTPUT_DIR}"
