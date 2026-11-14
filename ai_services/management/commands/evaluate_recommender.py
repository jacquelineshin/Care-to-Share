import json

from django.core.management.base import BaseCommand

from ai_services.evaluation import CASES_FILE, DATA_DIR, run_evaluation


class Command(BaseCommand):
    help = (
        "Run the labelled evaluation set against the recommender and "
        "report Hit@1, Hit@3, MRR, precision, false-positive rate, "
        "urgent-warning recall, quality (1-10) and latency."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--strategy",
            choices=["baseline", "hybrid"],
            default="hybrid",
            help="baseline = original semantic-only ranking; "
                 "hybrid = improved ranking (default).",
        )
        parser.add_argument(
            "--cases",
            default=str(CASES_FILE),
            help="Path to a JSON file of labelled cases "
                 "(default: ai_services/data/eval_cases.json).",
        )
        parser.add_argument(
            "--save",
            action="store_true",
            help="Write results to ai_services/data/eval_results_<strategy>.json",
        )

    def handle(self, *args, **options):
        strategy = options["strategy"]
        results = run_evaluation(strategy, options["cases"])

        header = (
            f"{'#':>2}  {'category':<13} {'symptom':<24} "
            f"{'returned topics':<48} {'Q':>2} {'ms':>6}"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        for row in results["rows"]:
            topics = ", ".join(item["topic"] for item in row["returned"]) or "(none)"
            flag = " [URGENT]" if row["urgent_shown"] else ""
            self.stdout.write(
                f"{row['id']:>2}  {row['category']:<13} "
                f"{row['symptom'][:24]:<24} {(topics + flag)[:48]:<48} "
                f"{row['quality']:>2} {row['latency_ms']:>6}"
            )

        self.stdout.write("")
        for key, value in results["summary"].items():
            self.stdout.write(f"{key:<22} {value}")

        if options["save"]:
            suffix = "" if options["cases"] == str(CASES_FILE) else "_holdout"
            path = DATA_DIR / f"eval_results_{strategy}{suffix}.json"
            path.write_text(json.dumps(results, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Saved {path.name}"))
