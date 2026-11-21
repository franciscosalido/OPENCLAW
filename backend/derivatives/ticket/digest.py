"""Codificação determinística da parte autorizável da boleta."""
import json
from decimal import Decimal
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.derivatives.ticket.models import Preview


def _money(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    # Potências grandes não precisam alocar uma cadeia proporcional ao expoente.
    if value.adjusted() >= 21:
        sign, digits, _ = value.as_tuple()
        coefficient = "".join(map(str, digits)).rstrip("0")
        mantissa = coefficient[0] + ("." + coefficient[1:] if len(coefficient) > 1 else "")
        return ("-" if sign else "") + mantissa + "E+" + str(value.adjusted())
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def canonical_bytes(preview: "Preview") -> bytes:
    """Representa os campos assinados em UTF-8 e preserva a ordem econômica das pernas."""
    preview = type(preview).model_validate(preview)
    payload = {
        "environment": preview.environment.value,
        "legs": [{"symbol": leg.symbol, "side": leg.side.value, "quantity": leg.quantity,
                  "limit_price": _money(leg.limit_price)}
                 for leg in preview.legs],
        "net_limit": _money(preview.net_limit), "gross_cap": _money(preview.gross_cap),
        "partial_exposure": _money(preview.partial_exposure),
        "send_deadline": preview.send_deadline.isoformat(),
        "order_validity": preview.order_validity.isoformat(),
        "quote_snapshot_id": preview.quote_snapshot_id,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(preview: "Preview") -> str:
    """Calcula SHA-256 hexadecimal dos bytes canônicos."""
    return sha256(canonical_bytes(preview)).hexdigest()
