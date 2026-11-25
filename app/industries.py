"""Industry configs.

This is the "all-in-one" idea: the main system is the same for every industry.
Only the YAML file changes. To add a new industry, add a new YAML file
in the `industries/` folder. No code change needed.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Industry(BaseModel):
    id: str
    name: str
    icon: str = "🏢"
    description: str
    system_prompt: str
    sample_questions: list[str] = Field(default_factory=list)
    # Tools the AI will use for this industry. Built in Step 6 (agents).
    tools: list[str] = Field(default_factory=list)
    # Step 2: ticket classifier. {category_name: description} + a few worked examples.
    ticket_categories: dict[str, str] = Field(default_factory=dict)
    ticket_examples: list[dict] = Field(default_factory=list)


def load_industries(folder: Path) -> dict[str, Industry]:
    """Read every *.yaml file in the folder and return {id: Industry}."""
    industries: dict[str, Industry] = {}
    for path in sorted(folder.glob("*.yaml")):
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        industry = Industry(**data)
        if industry.id in industries:
            raise ValueError(f"Duplicate industry id '{industry.id}' in {path.name}")
        industries[industry.id] = industry
    if not industries:
        raise ValueError(f"No industry files found in {folder}")
    return industries
