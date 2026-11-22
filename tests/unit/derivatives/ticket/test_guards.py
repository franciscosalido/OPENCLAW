"""Limites manuais de foto, idade, lado e validade."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.derivatives.ticket.guards import BookView, DeadlineRefusal, assess, check_deadlines
from backend.derivatives.ticket.paper_venue import PaperVenue
from backend.derivatives.ticket.replay import QuoteEvent, load_replay
from config.ticket_sim_config_model import TicketSimConfig, load_ticket_sim_config
from tests.unit.derivatives.ticket.test_replay import FIXTURE
from tests.unit.derivatives.ticket.test_sequencing import BUY, SELL, draft

NOW = datetime(2026, 11, 23, 14, tzinfo=UTC)
CLOSE = NOW.replace(hour=21)


def quote(symbol: str = "A", bid: str | None = ".95", ask: str | None = "1", bs: int = 50,
          size: int = 50, phase: str = "CONTINUOUS", age: float = 1) -> QuoteEvent:
    """Foto no instante relativo indicado em cada linha."""
    return QuoteEvent.model_validate(dict(seq=1, ts=NOW-timedelta(seconds=age), type="quote",
        symbol=symbol, bid=D(bid) if bid else None, bid_size=bs, ask=D(ask) if ask else None,
        ask_size=size, phase=phase))


@pytest.mark.parametrize(("photos", "legs", "level", "reasons"), [
    ([quote()], [BUY], "OK", ()), ([quote(age=5)], [BUY], "OK", ()),
    ([quote(age=5.000001)], [BUY], "BLOCKED", ("cotação vencida",)),
    ([quote(phase="AUCTION")], [BUY], "BLOCKED", ("leilão",)),
    ([quote(phase="SUSPENDED")], [BUY], "BLOCKED", ("suspensão",)),
    ([quote(bid="1")], [BUY], "BLOCKED", ("livro inválido",)),
    ([quote(bid="1.01")], [BUY], "BLOCKED", ("livro inválido",)),
    ([quote(ask=None,size=0)], [BUY], "BLOCKED", ("livro incompleto",)),
    ([quote("B",ask=None,size=0)], [SELL], "OK", ()), ([], [BUY], "BLOCKED", ("sem cotação",)),
    ([quote(bid=".90")], [BUY], "OK", ()),
    ([quote(bid=".89")], [BUY], "CAUTION", ("spread aberto",)),
    ([quote(size=9)], [BUY], "CAUTION", ("pouca profundidade",)),
    ([quote(size=10)], [BUY], "OK", ()),
    ([quote("B","1.50","1.55",9)], [SELL], "CAUTION", ("pouca profundidade",)),
    ([quote(bid=".89"),quote("B",phase="AUCTION")], [BUY,SELL], "BLOCKED",
     ("spread aberto","leilão")),
    ([quote(age=-1)], [BUY], "BLOCKED", ("tempo inválido",)),
], ids="G1 G2 G3 G4 G5 G6 G7 G8 G8-sell G9 G11 G12 G13 G14 G15 G16 G17".split())
def test_book(photos, legs, level, reasons) -> None:
    """Somente o lado executável exige profundidade."""
    view = BookView()
    for photo in photos:
        view.advance(photo)
    result = assess(legs, view, NOW, load_ticket_sim_config())
    assert (result.level, result.reasons) == (level, reasons)


def test_g10_global_permanent_gap() -> None:
    """Uma lacuna sem cotação invalida fotos antigas e novas."""
    view = BookView()
    view.advance(quote())
    view.advance(load_replay(FIXTURE).events[-1])
    view.advance(quote("B"))
    result = assess((BUY,SELL), view, NOW, load_ticket_sim_config())
    assert result.level == "BLOCKED" and result.reasons == ("perda de sequência",)*2


@pytest.mark.parametrize(("send","valid","now","reason"), [
    (15,21,"14:00",None), (15,21,"15:00",None), (15,21,"15:00:00.000001","prazo de envio vencido"),
    (21,21,"14:00",None), (21.5,21,"14:00","prazo de envio depois da validade"),
    (15,20,"14:00","validade que a venue não garante"), (15,21,"21:00","prazo de envio vencido"),
], ids="D1 D2 D3 D4 D5 D6 D7".split())
def test_deadlines(send, valid, now, reason) -> None:
    """Envio inclusivo e validade nativa da venue."""
    midnight = NOW.replace(hour=0)
    t = draft(BUY, SELL).model_copy(update=dict(send_deadline=midnight+timedelta(hours=send),
                                                order_validity=midnight+timedelta(hours=valid)))
    instant = datetime.fromisoformat(f"2026-11-23T{now}+00:00")
    if reason:
        with pytest.raises(DeadlineRefusal, match=reason):
            check_deadlines(t, instant, PaperVenue(CLOSE))
    else:
        check_deadlines(t, instant, PaperVenue(CLOSE))


@pytest.mark.parametrize("overrides", [dict(max_quote_age_s=5), dict(max_spread_ticks=10.0),
                                       dict(max_quote_age_s=-1.0), dict(max_spread_ticks=-1)])
def test_strict_config(overrides) -> None:
    """O YAML exige ambos os parâmetros com os tipos declarados."""
    with pytest.raises(ValidationError):
        TicketSimConfig.model_validate(load_ticket_sim_config().model_dump() | overrides)
