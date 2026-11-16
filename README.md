# Care to Share

A Django app that helps patients prepare for doctor visits: track appointments, record symptoms and questions, print a pre-visit summary, use the visit companion, and follow post-visit instructions. A local sentence-embedding model recommends educational articles for each health concern.

**Parts 4 & 5 (evaluation, deployment, cost, security):** see [EVALUATION_AND_DEPLOYMENT.md](EVALUATION_AND_DEPLOYMENT.md).

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # 30 articles + embeddings + a demo user
python manage.py runserver
```

Open http://localhost:8000. The demo user is `demo`; the password is in `ai_services/management/commands/seed_demo.py`. The first run downloads the `all-MiniLM-L6-v2` model (~90 MB).

## Production-mode deployment (local)

```bash
./deploy_local.sh        # gunicorn, DEBUG=False, model pre-loaded → http://localhost:8000
```

This installs the dependencies, generates a secret key (stored in git-ignored `.env.local`), migrates, seeds the article library and the demo user, then serves the app. See section 5.1 of [EVALUATION_AND_DEPLOYMENT.md](EVALUATION_AND_DEPLOYMENT.md) for why the deployment is local, and for the Render Blueprint (`render.yaml`) that deploys the same app to the cloud.

## Commands

| Command | Purpose |
|---|---|
| `python manage.py seed_resources [--embed]` | Load or refresh the article library |
| `python manage.py evaluate_recommender --strategy {baseline,improved} [--cases FILE] [--save]` | Run the labelled evaluation set |
| `python manage.py test` | Run the tests |
| `gunicorn config.wsgi:application -c gunicorn.conf.py` | Production server |
