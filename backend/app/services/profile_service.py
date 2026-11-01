"""The writer profile (who the writer is): one Markdown record per user.

content_config/user_profile.md remains the backfill for the pre-multi-user
owner; new users choose from the neutral templates in profile_templates/."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import WriterProfile

MAX_PROFILE_CHARS = 8000
_TEMPLATE_IDS = (
    "junior_engineer",
    "senior_engineer",
    "engineering_manager",
    "product_lead",
    "platform_lead_architect",
)


def _parse_template(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"profile template {path.name} has no front matter")

    metadata: dict[str, str] = {}
    body_start = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = index + 1
            break
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()

    if body_start is None:
        raise ValueError(f"profile template {path.name} has unclosed front matter")
    for field in ("label", "description"):
        if not metadata.get(field):
            raise ValueError(f"profile template {path.name} is missing {field}")

    return {
        "id": path.stem,
        "label": metadata["label"],
        "description": metadata["description"],
        "profile_md": "\n".join(lines[body_start:]).strip(),
    }


def templates() -> list[dict]:
    template_dir = Path(settings.profile_templates_path)
    return [_parse_template(template_dir / f"{template_id}.md")
            for template_id in _TEMPLATE_IDS]


def get_profile(db: Session, owner_id: str) -> WriterProfile | None:
    return db.get(WriterProfile, owner_id)


def profile_text(db: Session, owner_id: str) -> str:
    profile = get_profile(db, owner_id)
    return profile.profile_md if profile else ""


def save_profile(db: Session, owner_id: str, profile_md: str) -> WriterProfile:
    profile = get_profile(db, owner_id)
    if profile is None:
        profile = WriterProfile(owner_id=owner_id)
        db.add(profile)
    profile.profile_md = profile_md
    profile.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return profile
