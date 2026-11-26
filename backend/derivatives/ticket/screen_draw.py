"""Desenhos da tela da boleta: só posicionam números já calculados; não decidem nada."""
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction
from html import escape

WIDTH, LEFT, RIGHT = 600, 60, 540
CURVE_TOP, CURVE_BOTTOM = 24, 104


def _place(value: Fraction, low: Fraction, high: Fraction, start: int, end: int) -> str:
    """Coordenada com uma casa; intervalo de largura zero fica no meio."""
    if high == low:
        return f"{(start + end) / 2:.1f}"
    return f"{float(start + (value - low) / (high - low) * (end - start)):.1f}"


def ruler(marks: Sequence[tuple[str, Decimal, str]], label: str) -> str:
    """Régua horizontal: uma marca por valor distinto, rótulos iguais unidos por « = »."""
    merged: dict[Decimal, tuple[list[str], str]] = {}
    for name, value, shown in marks:
        merged.setdefault(value, ([], shown))[0].append(name)
    low, high = Fraction(min(merged)), Fraction(max(merged))
    parts = [f'<svg viewBox="0 0 {WIDTH} 70" role="img" aria-label="{escape(label)}">',
             f'<line x1="{LEFT}" y1="14" x2="{RIGHT}" y2="14" class="trilho"/>']
    for value in sorted(merged):
        names, shown = merged[value]
        x = _place(Fraction(value), low, high, LEFT, RIGHT)
        parts.append(f'<line x1="{x}" y1="6" x2="{x}" y2="26" class="marco"/>'
                     f'<text x="{x}" y="42" class="t" text-anchor="middle">'
                     f'{escape(" = ".join(names))}</text>'
                     f'<text x="{x}" y="60" class="v" text-anchor="middle">{escape(shown)}</text>')
    return "".join(parts) + "</svg>"


def curve(points: Sequence[tuple[Decimal, Decimal, str, str]], final_slope: Decimal,
          breakevens: Sequence[tuple[Decimal, str]], label: str) -> str:
    """Resultado no vencimento: reta entre as quebras, da janela dos strikes para fora."""
    spots = [Fraction(point[0]) for point in points]
    results = [Fraction(point[1]) for point in points]
    first, last = spots[1], spots[-1]
    margin = last - first if last > first else Fraction(1)
    low, high = max(first - margin, Fraction(0)), last + margin
    left = results[0] + (results[1] - results[0]) * (low - spots[0]) / (first - spots[0])
    line = [(low, left), *zip(spots[1:], results[1:], strict=True),
            (high, results[-1] + Fraction(final_slope) * margin)]
    floor = min(Fraction(0), *(y for _, y in line))
    ceiling = max(Fraction(0), *(y for _, y in line))

    def xy(spot: Fraction, result: Fraction) -> tuple[str, str]:
        return (_place(spot, low, high, LEFT, RIGHT),
                _place(result, ceiling, floor, CURVE_TOP, CURVE_BOTTOM))

    zero = xy(low, Fraction(0))[1]
    parts = [f'<svg viewBox="0 0 {WIDTH} 154" role="img" aria-label="{escape(label)}">',
             f'<line x1="{LEFT}" y1="{zero}" x2="{RIGHT}" y2="{zero}" class="zero"/>',
             '<polyline class="linha" points="'
             + " ".join(",".join(xy(spot, result)) for spot, result in line) + '"/>']
    for spot, result, (_, _, shown, worth) in zip(spots[1:], results[1:], points[1:],
                                                  strict=True):
        x, y = xy(spot, result)
        tone, shift = ("v neg", 16) if result < 0 else ("v", -8)
        parts.append(f'<text x="{x}" y="136" class="t" text-anchor="middle">{escape(shown)}'
                     f'</text><text x="{x}" y="{float(y) + shift:.1f}" class="{tone}" '
                     f'text-anchor="middle">{escape(worth)}</text>')
    for value, shown in breakevens:
        if low <= Fraction(value) <= high:
            x = xy(Fraction(value), Fraction(0))[0]
            parts.append(f'<line x1="{x}" y1="{CURVE_TOP - 8}" x2="{x}" y2="{CURVE_BOTTOM + 20}" '
                         f'class="eq"/><text x="{x}" y="151" class="v" text-anchor="middle">'
                         f"{escape(shown)}</text>")
    return "".join(parts) + "</svg>"
