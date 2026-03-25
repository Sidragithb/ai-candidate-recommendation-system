from django.core.management.base import BaseCommand, CommandError

from apps.ai.services.hybrid_search import HybridSearchService
from apps.ai.tasks import process_candidate_resume_task, update_job_embedding_task
from apps.candidates.models import Candidate
from apps.jobs.models import Job


class Command(BaseCommand):
    help = "Reprocess existing candidates so fit score, breakdown, ranking reasons, and processing state are backfilled."

    def add_arguments(self, parser):
        parser.add_argument("--candidate-id", type=int, help="Reprocess a single candidate by ID.")
        parser.add_argument("--job-id", type=int, help="Reprocess candidates for one job only.")
        parser.add_argument("--limit", type=int, help="Maximum number of candidates to process.")
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Process only candidates missing fit score, breakdown, reasons, or processed timestamp.",
        )
        parser.add_argument(
            "--async",
            dest="run_async",
            action="store_true",
            help="Queue background tasks instead of processing inline.",
        )

    def handle(self, *args, **options):
        candidate_id = options.get("candidate_id")
        job_id = options.get("job_id")
        limit = options.get("limit")
        only_missing = options.get("only_missing", False)
        run_async = options.get("run_async", False)

        queryset = Candidate.objects.select_related("job").order_by("id")
        if candidate_id:
            queryset = queryset.filter(id=candidate_id)
        if job_id:
            queryset = queryset.filter(job_id=job_id)
        if only_missing:
            queryset = queryset.filter(
                fit_score=0,
                last_processed_at__isnull=True,
            ) | queryset.filter(fit_breakdown={}) | queryset.filter(ranking_reasons=[])
            queryset = queryset.select_related("job").order_by("id")
        if limit:
            queryset = queryset[:limit]

        candidates = list(queryset)
        if not candidates:
            raise CommandError("No matching candidates found for reprocessing.")

        job_ids = sorted({candidate.job_id for candidate in candidates})
        self.stdout.write(self.style.NOTICE(f"Preparing {len(job_ids)} job(s) and {len(candidates)} candidate(s)."))

        for current_job_id in job_ids:
            if not Job.objects.filter(id=current_job_id).exists():
                continue
            if run_async:
                update_job_embedding_task.delay(current_job_id)
            else:
                update_job_embedding_task.apply(args=[current_job_id])

        processed = 0
        failed = 0
        for candidate in candidates:
            try:
                if run_async:
                    process_candidate_resume_task.delay(candidate.id)
                else:
                    process_candidate_resume_task.apply(args=[candidate.id])
                processed += 1
                self.stdout.write(self.style.SUCCESS(f"Processed candidate {candidate.id} - {candidate.full_name}"))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"Failed candidate {candidate.id}: {exc}"))

        for current_job_id in job_ids:
            HybridSearchService().invalidate_job_cache(current_job_id)
        HybridSearchService().invalidate_job_cache(None)

        self.stdout.write(
            self.style.SUCCESS(
                f"Reprocessing finished. Success: {processed}, Failed: {failed}, Total: {len(candidates)}"
            )
        )
