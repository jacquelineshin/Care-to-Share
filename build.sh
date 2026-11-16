#!/usr/bin/env bash
# Render build step: install, collect static files, migrate, load the
# resource library and download the embedding model + pre-compute
# resource embeddings so the first user request is fast.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py seed_resources --embed
