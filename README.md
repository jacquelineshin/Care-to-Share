# Care to Share

A Django app that helps patients prepare for doctor visits: track appointments, record symptoms and questions, print a pre-visit summary, and follow post-visit instructions.

**AI feature:** each health concern is matched to trustworthy educational articles using a local sentence-embedding model. Red-flag symptoms (possible emergencies, self-harm) trigger an urgent-care or 988 banner. See [AI_REPORT.md](AI_REPORT.md) for the design, model choice, workflow, reliability handling, and evaluation.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # loads 30 articles, computes embeddings, creates a demo user
python manage.py runserver
```

Open http://localhost:8000. The demo login is user `demo`; the password is in `ai_services/management/commands/seed_demo.py`.

The first run downloads the `all-MiniLM-L6-v2` model (~90 MB) from Hugging Face. After that it runs fully offline.

## Useful commands

| Command | Purpose |
|---|---|
| `python manage.py seed_resources [--embed]` | Load or refresh the educational-resource library (`ai_services/data/resources.json`) |
| `python manage.py evaluate_recommender --strategy hybrid` | Run the labelled evaluation set (use `--strategy baseline` for the original algorithm, `--cases <file>` for the held-out set, `--save` to write results) |
| `python manage.py test` | Run the unit and integration tests |

## Project layout

- `appointments/`: core app (models, views, templates)
- `ai_services/resource_recommender.py`: embedding retrieval, confidence-tiered ranking, keyword fallback
- `ai_services/safety.py`: rule-based red-flag screening
- `ai_services/evaluation.py`: evaluation metrics and quality rubric
- `ai_services/data/`: article library, evaluation cases, saved evaluation results
