#!/bin/sh
set -eux
for addon in */ ; do
  if [ -f "${addon}requirements.txt" ]; then
    pip install -r "${addon}requirements.txt"
  fi
  if [ "$DEV_MODE" = "true" ] && [ -f "${addon}requirements-dev.txt" ]; then
    pip install -r "${addon}requirements-dev.txt"
  fi
done