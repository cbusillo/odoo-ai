#!/bin/bash
set -e

echo "Overwriting from production..."
docker compose stop odoo database
docker compose run --rm overwrite-from-upstream
echo "Finished pulling from prod."

echo "Pruning docker images and volumes..."
docker container prune -f
docker image prune -af
docker volume prune -f
echo "Finished pruning."