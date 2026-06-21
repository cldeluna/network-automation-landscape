"""Pre-flight validation of a proposed data.yml against the landscape2 schema.

This is the same JSON Schema (``schemas/landscape2-data-schema.json``) that the
CI workflow runs via ``landscape2 validate data``. Running it here moves the
gate from post-push to authoring time: the form rejects a bad item before a PR
is ever opened, instead of the contributor learning about it from a red CI run.
"""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft7Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "landscape2-data-schema.json"


@lru_cache(maxsize=1)
def _validator() -> Draft7Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    # format_checker enforces the schema's `format: uri` on homepage_url etc.
    return Draft7Validator(schema, format_checker=FormatChecker())


def validate_landscape(data: dict) -> list[str]:
    """Validate a full landscape document. Returns a list of error messages
    (empty when valid). ``data`` is the plain-dict form of the proposed
    data.yml (round-trip types are JSON-coerced first)."""
    plain = json.loads(json.dumps(data, default=str))
    errors = []
    for err in sorted(_validator().iter_errors(plain), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors
