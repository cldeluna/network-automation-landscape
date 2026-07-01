"""Pydantic form models for tool submission.

These close the "free-string" gap found in Phase 1: ``project`` and ``tag``
were lenient strings in the data, so typos and off-vocabulary values slipped
in. Here they are validated against controlled vocabularies up front, before a
PR is ever opened.
"""

from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from api.models import NAF_TAXONOMY, NAFComponent

# Maturity / business-model values, mirrored from settings.yml `featured_items`
# (field: maturity). This fork repurposes landscape2's `project` field to carry
# the business model; these are the allowed values.
MATURITY_VALUES: list[str] = [
    "full-open-source",
    "oss-with-paid-support",
    "freemium",
    "commercial-with-trial",
    "commercial-only",
    "enterprise",
    "saas",
    "hybrid",
    "inactive",
    "deprecated",
    "end-of-life",
    "archived",
    "free-restrictive",
    "closed-core",
]

Maturity = Enum("Maturity", {v.replace("-", "_"): v for v in MATURITY_VALUES}, type=str)

# Accepted `extra.tag` values: the 7 NAF components plus the non-NAF values
# already in use in data.yml (labbing/SDK/tooling that don't map to NAF).
NON_NAF_TAGS: list[str] = ["sdk", "tool", "lab", "execution"]
ALLOWED_TAGS: list[str] = [c.value for c in NAFComponent] + NON_NAF_TAGS

# Optional free-text `extra.*` summary fields we let the form carry through.
SUMMARY_FIELDS: list[str] = [
    "documentation_url",
    "summary_use_case",
    "summary_business_use_case",
    "summary_integration",
    "summary_tags",
    "summary_personas",
    "summary_features",
    "summary_release_rate",
    "blog_url",
]


class ContactForm(BaseModel):
    name: str
    role: str | None = None
    email: EmailStr | None = None
    github: str | None = None
    voluntary: bool = True


class ToolForm(BaseModel):
    """A tool add/edit submission coming from the web form."""

    # --- identity / placement ------------------------------------------------
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subcategory: str = Field(min_length=1)

    # --- core data.yml item fields ------------------------------------------
    # homepage_url and logo are REQUIRED by the landscape2 data schema
    # (required: [name, homepage_url, logo]); enforce them up front.
    homepage_url: str = Field(min_length=1)
    logo: str = Field(min_length=1)  # filename under logos/ (or set by an upload)
    # Optional off-site logo URL: stored as-is in the sidecar, not fetched and
    # not used by the static build. Surfaced via the API for later UI use.
    logo_url: str | None = None
    description: str | None = None
    repo_url: str | None = None
    project: Maturity | None = None
    crunchbase: str | None = None
    twitter: str | None = None

    # --- extra block ---------------------------------------------------------
    tags: list[str] = Field(default_factory=list)
    summaries: dict[str, str] = Field(default_factory=dict)

    # --- sidecar (extended_data.yml) ----------------------------------------
    contacts: list[ContactForm] = Field(default_factory=list)
    naf_component: str | None = None
    naf_subfunctions: list[str] = Field(default_factory=list)
    secondary_naf_components: list[str] = Field(default_factory=list)

    # --- submitter (PR attribution / moderation) ----------------------------
    submitter_name: str = Field(min_length=1)
    submitter_email: EmailStr

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in ALLOWED_TAGS]
        if bad:
            raise ValueError(
                f"Unknown tag(s) {bad}. Allowed: {', '.join(ALLOWED_TAGS)}"
            )
        return v

    @field_validator("naf_component", "secondary_naf_components")
    @classmethod
    def _validate_naf_components(cls, v):
        values = [v] if isinstance(v, str) else (v or [])
        bad = [c for c in values if c not in NAF_TAXONOMY]
        if bad:
            raise ValueError(
                f"Unknown NAF component(s) {bad}. Allowed: {', '.join(NAF_TAXONOMY)}"
            )
        return v

    @field_validator("logo_url")
    @classmethod
    def _validate_logo_url(cls, v: str | None) -> str | None:
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("logo_url must be an http(s) URL.")
        return v

    @field_validator("summaries")
    @classmethod
    def _validate_summaries(cls, v: dict[str, str]) -> dict[str, str]:
        bad = [k for k in v if k not in SUMMARY_FIELDS]
        if bad:
            raise ValueError(f"Unknown summary field(s) {bad}.")
        return v

    @model_validator(mode="after")
    def _validate_subfunctions(self) -> "ToolForm":
        if self.naf_subfunctions:
            allowed = NAF_TAXONOMY.get(self.naf_component or "", [])
            bad = [s for s in self.naf_subfunctions if s not in allowed]
            if bad:
                raise ValueError(
                    f"Sub-function(s) {bad} are not valid for NAF component "
                    f"'{self.naf_component}'. Allowed: {allowed}"
                )
        return self

    # --- projection to storage shapes ---------------------------------------

    def to_data_item(self) -> dict:
        """Build the ordered data.yml item dict (only non-empty keys)."""
        item: dict = {"name": self.name}
        if self.project is not None:
            item["project"] = self.project.value
        if self.description:
            item["description"] = self.description
        if self.homepage_url:
            item["homepage_url"] = self.homepage_url
        if self.logo:
            item["logo"] = self.logo
        if self.repo_url:
            item["repo_url"] = self.repo_url
        if self.crunchbase:
            item["crunchbase"] = self.crunchbase
        if self.twitter:
            item["twitter"] = self.twitter

        extra: dict = {}
        for key in SUMMARY_FIELDS:
            val = self.summaries.get(key)
            if val:
                extra[key] = val
        if self.tags:
            extra["tag"] = list(self.tags)
        if extra:
            item["extra"] = extra
        return item

    def to_sidecar(self) -> dict:
        """Build the sidecar fragments for extended_data.yml.

        Returns a dict with optional ``contacts`` (list) and ``naf_mapping``
        (dict) keys. Empty pieces are omitted so we never write noise.
        """
        out: dict = {}
        if self.contacts:
            out["contacts"] = [
                c.model_dump(exclude_none=True) for c in self.contacts
            ]
        if self.logo_url:
            out["logo_url"] = self.logo_url
        mapping: dict = {}
        if self.naf_component:
            mapping["naf_component"] = self.naf_component
        if self.naf_subfunctions:
            mapping["naf_subfunctions"] = list(self.naf_subfunctions)
        if self.secondary_naf_components:
            mapping["secondary_naf_components"] = list(self.secondary_naf_components)
        if mapping:
            out["naf_mapping"] = mapping
        return out
