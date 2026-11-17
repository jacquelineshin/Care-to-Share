#!/usr/bin/env bash
# One-command local production deployment of Care to Share.
#
#   ./deploy_local.sh            # install, migrate, seed, serve on :8000
#   PORT=9000 ./deploy_local.sh  # different port
#
# Runs the same stack as the cloud configuration (gunicorn, DEBUG=False,
# WhiteNoise static files, env-var settings, model warm-up), but over
# plain HTTP on this machine with a local SQLite database.
set -o errexit
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
export PORT="${PORT:-8000}"

if [ ! -d .venv ]; then
    echo "==> Creating virtual environment"
    "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Production settings. A random secret key is generated once and kept in
# .env.local (git-ignored) so sessions survive restarts.
if [ ! -f .env.local ]; then
    echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" > .env.local
fi
set -a
# shellcheck disable=SC1091
source .env.local
set +a
export DJANGO_DEBUG=False
export DJANGO_HTTPS=False
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export HF_HOME="${HF_HOME:-$PWD/.hf_cache}"

# Optional: the AI pre-visit summary's "improve wording" step uses a local
# Ollama server. Without it, that one button shows an error message and
# everything else works.
if command -v ollama >/dev/null 2>&1; then
    echo "==> Pulling Ollama model qwen2.5:0.5b (AI summary wording)"
    ollama pull qwen2.5:0.5b || echo "    (could not pull; is 'ollama serve' running?)"
else
    echo "==> Ollama not installed: AI summary wording suggestions will be unavailable"
    echo "    Install from https://ollama.com and run 'ollama serve' to enable them."
fi

echo "==> Preparing database, static files and AI models"
python manage.py collectstatic --no-input --verbosity 0
python manage.py migrate --no-input --verbosity 0
python manage.py seed_demo

echo "==> Serving on http://localhost:$PORT  (health check: /healthz/)"
exec gunicorn config.wsgi:application -c gunicorn.conf.py
