"""Configuração sintética do replay local."""
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, InstanceOf


class TicketSimConfig(BaseModel):
    """Critérios explícitos de idade e spread do simulador."""
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", allow_inf_nan=False)
    max_quote_age_s: Annotated[InstanceOf[float], Field(ge=0, lt=float("inf"))]
    max_spread_ticks: int = Field(ge=0)


def load_ticket_sim_config(path: Path | None = None) -> TicketSimConfig:
    """Carrega e valida o YAML local sem valores substitutos."""
    source = path or Path(__file__).with_name("ticket_sim.yaml")
    return TicketSimConfig.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))
