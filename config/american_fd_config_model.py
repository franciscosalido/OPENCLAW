"""Perfil local do diagnóstico americano por diferenças finitas."""
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AmericanFdConfig(BaseModel):
    """Perfil FD; space_nodes conta divisões, com um nó adicional nas bordas."""
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, allow_inf_nan=False,
        revalidate_instances="always",
    )
    space_nodes: int = Field(ge=2, multiple_of=2)
    time_steps: int = Field(gt=0)
    width_stdevs: float = Field(gt=0)
    rannacher_steps: int = Field(ge=0)
    bracket_lo: float = Field(gt=0)
    bracket_hi: float = Field(gt=0)
    max_iterations: int = Field(ge=1, le=64)
    tol_price_rel: float = Field(gt=0)
    tol_vol: float = Field(gt=0)
    divergence_vol: float = Field(gt=0)
    low_sensitivity_price: float = Field(gt=0)

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.bracket_lo >= self.bracket_hi or self.rannacher_steps > self.time_steps:
            raise ValueError("faixa de sigma ou partida de Rannacher inválida")
        return self


def load_american_fd_config(path: Path | None = None) -> AmericanFdConfig:
    """Lê e valida o perfil, sem padrão de código ou arquivo alternativo."""
    resolved = path if path is not None else Path(__file__).with_name("american_fd.yaml")
    try:
        content = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError("YAML de diferenças finitas inválido") from exc
    return AmericanFdConfig.model_validate(content)
