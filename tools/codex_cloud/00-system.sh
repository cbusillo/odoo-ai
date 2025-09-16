#!/usr/bin/env bash

set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

ensure_root

export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y git openssh-client rsync software-properties-common curl ripgrep ca-certificates postgresql postgresql-client

if command -v add-apt-repository >/dev/null 2>&1; then
  add-apt-repository -y ppa:xtradeb/apps
  apt-get update -y
fi

apt-get install -y chromium fonts-liberation libu2f-udev || apt-get install -y chromium-browser || true

apt-get clean
rm -rf /var/lib/apt/lists/*

log "System packages ready"
