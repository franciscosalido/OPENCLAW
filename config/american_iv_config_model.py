"""Configuração local da IV americana, independente do contrato da Fase 1."""

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AmericanIvConfig(BaseModel):
    """Faixa e tolerâncias da inversão CRR, fornecidas no YAML sem defaults locais."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False, revalidate_instances="always",
    )

    bracket_lo: float = Field(gt=0)
    bracket_hi: float = Field(gt=0)
    max_iterations: int = Field(gt=0, le=64)
    default_steps: int = Field(ge=1, le=4999)
    tol_price_rel: float = Field(gt=0)
    tol_vol: float = Field(gt=0)

    @field_validator("default_steps", mode="before")
    @classmethod
    def _require_actual_int(cls, value: object) -> int:
        if type(value) is not int:
            raise ValueError("default_steps exige inteiro sem coerção")
        return value

    @model_validator(mode="after")
    def _check_bracket(self) -> Self:
        if self.bracket_lo >= self.bracket_hi:
            raise ValueError("american_iv exige bracket_lo menor que bracket_hi")
        return self


def load_american_iv_config(path: Path | None = None) -> AmericanIvConfig:
    """Lê o YAML de IV americana; arquivo ausente ou inválido não tem fallback."""
    resolved = path if path is not None else Path(__file__).with_name("american_iv.yaml")
    try:
        content = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError("YAML de IV americana inválido") from exc
    return AmericanIvConfig.model_validate(content)
