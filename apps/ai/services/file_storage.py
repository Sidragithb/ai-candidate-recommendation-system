from pathlib import Path
from uuid import uuid4

from django.conf import settings


class FileStorageService:
    def save_resume(self, original_filename: str, content: bytes) -> str:
        uploads_dir = Path(settings.MEDIA_ROOT) / "resumes"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        extension = Path(original_filename).suffix
        stored_name = f"{uuid4().hex}{extension}"
        destination = uploads_dir / stored_name
        destination.write_bytes(content)
        return str(destination)
