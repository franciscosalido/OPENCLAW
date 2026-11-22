"""Configuração sintética do replay local."""
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TicketSimConfig(BaseModel):
    """Critérios explícitos de idade e spread do simulador."""
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", allow_inf_nan=False)
    max_quote_age_s: float = Field(ge=0)
    max_spread_ticks: int = Field(ge=0)

    @field_validator("max_quote_age_s", mode="before")
    @classmethod
    def _strict_float(cls, value: object) -> float:
        if type(value) is not float:
            raise ValueError("idade exige float")
        return value


def load_ticket_sim_config(path: Path | None = None) -> TicketSimConfig:
    """Carrega e valida o YAML local sem valores substitutos."""
    source = path or Path(__file__).with_name("ticket_sim.yaml")
    return TicketSimConfig.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))
