import hashlib
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.ai.services.document_parser import DocumentParserService
from apps.ai.services.embedding import EmbeddingService
from apps.ai.services.resume_parser import ResumeParsingService
from apps.ai.services.scoring import FitScoringService
from apps.ai.services.text import split_skills
from apps.ai.services.vector_store import VectorSearchService
from apps.candidates.models import Candidate
from apps.jobs.models import Job

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".txt"}


class ResumeIngestionService:
    def create_candidate(
        self,
        *,
        job: Job,
        full_name: str,
        email: str,
        skills: str,
        resume_name: str,
        file_bytes: bytes,
    ) -> Candidate:
        resume_extension = Path(resume_name).suffix.lower()
        if resume_extension not in ALLOWED_RESUME_EXTENSIONS:
            raise ValueError("Unsupported resume format. Allowed formats: PDF, DOCX, TXT.")

        resume_hash = hashlib.sha256(file_bytes).hexdigest()
        if Candidate.objects.filter(job=job, email__iexact=email).exists():
            raise ConflictError("A candidate with this email has already applied for this job.")
        if Candidate.objects.filter(job=job, resume_hash=resume_hash).exists():
            raise ConflictError("This resume content has already been uploaded for this job.")

        candidate = Candidate(
            job=job,
            full_name=full_name,
            email=email,
            skills=skills,
            resume_hash=resume_hash,
            processing_status=Candidate.ProcessingStatus.QUEUED,
        )
        candidate.resume_file.save(resume_name, ContentFile(file_bytes), save=False)
        candidate.save()
        return candidate

    def process_candidate(self, candidate_id: int) -> Candidate:
        candidate = Candidate.objects.select_related("job").get(id=candidate_id)
        parsing_service = ResumeParsingService()
        candidate.processing_status = Candidate.ProcessingStatus.PROCESSING
        candidate.processing_error = ""
        candidate.save(update_fields=["processing_status", "processing_error"])
        try:
            file_bytes = candidate.resume_file.read() if candidate.resume_file else b""
            resume_name = candidate.resume_file.name if candidate.resume_file else f"{candidate.id}.pdf"
            resume_text = DocumentParserService().extract_text(resume_name, file_bytes)
            if not resume_text.strip():
                raise ValueError("Could not extract readable text from the uploaded resume.")

            parsed = parsing_service.parse_resume(
                resume_text,
                hinted_skills=split_skills(candidate.skills),
            )
            skills = parsing_service.sanitize_skills([*split_skills(candidate.skills), *parsed.get("skills", [])])
            search_document = "\n".join(
                filter(
                    None,
                    [
                        candidate.full_name,
                        " ".join(skills),
                        resume_text,
                        parsed.get("degree_title", ""),
                        parsed.get("education_institution", ""),
                    ],
                )
            )
            embedding = EmbeddingService().embed_text(search_document)
            fit = FitScoringService().score_candidate_against_job(
                candidate_embedding=embedding,
                candidate_skills=skills,
                resume_text=resume_text,
                candidate_years_experience=float(parsed.get("estimated_years_experience") or 0.0),
                candidate_education_level=str(parsed.get("education_level", "")),
                job_embedding=(
                    candidate.job.embedding
                    or EmbeddingService().embed_text(candidate.job.search_document or candidate.job.description)
                ),
                job_required_skills=candidate.job.normalized_required_skills or split_skills(candidate.job.required_skills),
                job_description=candidate.job.description,
            )

            candidate.resume_text = resume_text
            candidate.parsed_resume = parsed
            candidate.parsed_skills = skills
            candidate.skills = ",".join(skills)
            candidate.embedding = embedding
            candidate.search_document = search_document
            candidate.estimated_years_experience = parsed.get("estimated_years_experience") or 0.0
            candidate.experience_score = parsed.get("experience_score") or 0.0
            candidate.education_level = parsed.get("education_level", "")
            candidate.degree_title = parsed.get("degree_title", "")
            candidate.education_institution = parsed.get("education_institution", "")
            candidate.education_score = parsed.get("education_score") or 0.0
            candidate.fit_score = fit["fit_score"]
            candidate.fit_breakdown = fit["breakdown"]
            candidate.ranking_reasons = fit["reasons"]
            candidate.vector_indexed = False
            candidate.processing_status = Candidate.ProcessingStatus.COMPLETED
            candidate.processing_error = ""
            candidate.last_processed_at = timezone.now()
            candidate.save()

            VectorSearchService().index_candidate(
                candidate_id=candidate.id,
                job_id=candidate.job_id,
                full_name=candidate.full_name,
                email=candidate.email,
                skills=skills,
                resume_text=candidate.resume_text,
                years_experience=float(candidate.estimated_years_experience),
                experience_score=float(candidate.experience_score),
                education_level=candidate.education_level,
                degree_title=candidate.degree_title,
                education_institution=candidate.education_institution,
                education_score=float(candidate.education_score),
                fit_score=float(candidate.fit_score),
                fit_breakdown=dict(candidate.fit_breakdown or {}),
                ranking_reasons=list(candidate.ranking_reasons or []),
                embedding=embedding,
            )
            candidate.vector_indexed = True
            candidate.save(update_fields=["vector_indexed"])
        except Exception as exc:
            candidate.processing_status = Candidate.ProcessingStatus.FAILED
            candidate.processing_error = str(exc)
            candidate.save(update_fields=["processing_status", "processing_error"])
            raise
        return candidate


class ConflictError(Exception):
    pass
