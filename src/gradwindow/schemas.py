from __future__ import annotations

from pathlib import Path

from .io import write_json
from .models import (
    ApplicantCategory,
    ApplicationWindow,
    EvidenceSnapshot,
    ParserSource,
    Prediction,
    Programme,
    ProgrammeGroup,
    University,
    WindowPolicy,
)
from .paths import SCHEMA_DIR

SCHEMA_MODELS = {
    "applicant-category.schema.json": ApplicantCategory,
    "application-window.schema.json": ApplicationWindow,
    "evidence-snapshot.schema.json": EvidenceSnapshot,
    "parser-source.schema.json": ParserSource,
    "prediction.schema.json": Prediction,
    "programme.schema.json": Programme,
    "programme-group.schema.json": ProgrammeGroup,
    "university.schema.json": University,
    "window-policy.schema.json": WindowPolicy,
}


def export_schemas(output_dir: Path = SCHEMA_DIR) -> list[Path]:
    written = []
    for filename, model in SCHEMA_MODELS.items():
        path = output_dir / filename
        write_json(path, model.model_json_schema(by_alias=True))
        written.append(path)
    return written
