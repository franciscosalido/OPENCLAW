"""Diferenças finitas em ln S: Crank–Nicolson, Rannacher e separação de operador."""
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from backend.derivatives.domain.models import ExerciseStyle, OptionKind

FD_MODEL: Final = "fd_cn_os_v1"


class FdRefusalCode(StrEnum):
    """Classifica entradas que não produzem um preço."""
    INVALID_INPUT_TYPE = "invalid_input_type"
    NON_FINITE_INPUT = "non_finite_input"
    INPUT_OUT_OF_DOMAIN = "input_out_of_domain"
    ZERO_VOLATILITY = "zero_volatility"
    INVALID_GRID = "invalid_grid"
    GRID_NOT_ADMISSIBLE = "grid_not_admissible"
    NOT_REPRESENTABLE = "not_representable"


class FdRefusal(Exception):
    """Recusa de preço sem resultado numérico."""

    def __init__(self, code: FdRefusalCode) -> None:
        """Conserva o código estável do chamador."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class FdGrid:
    """Divisões espaciais (mais um nó), passos, largura e pares Rannacher."""
    space_nodes: int
    time_steps: int
    width_stdevs: float
    rannacher_steps: int


_Status = Literal["ok", "below_intrinsic", "unbracketed", "not_identifiable", "no_convergence",
                  "grid_not_admissible", "invalid_input"]


@dataclass(frozen=True, slots=True)
class FdIvResult:
    """Estado da inversão, com sigma apenas para uma solução identificada."""
    status: _Status
    sigma: float | None
    iterations: int = 0


def _validate(kind: OptionKind, style: ExerciseStyle, spot: float, strike: float, years: float,
              rate: float, q: float, sigma: float, grid: FdGrid) -> None:
    nums = (spot, strike, years, rate, q, sigma)
    if (type(kind) is not OptionKind or type(style) is not ExerciseStyle or type(grid) is not FdGrid
            or any(type(x) is not float for x in nums)):
        raise FdRefusal(FdRefusalCode.INVALID_INPUT_TYPE)
    if not all(map(math.isfinite, nums)):
        raise FdRefusal(FdRefusalCode.NON_FINITE_INPUT)
    nx, nt, width, ran = grid.space_nodes, grid.time_steps, grid.width_stdevs, grid.rannacher_steps
    if (type(nx) is not int or type(nt) is not int or type(ran) is not int
            or type(width) is not float or not math.isfinite(width) or width <= 0
            or nx < 2 or nx % 2 or nt < 1 or not 0 <= ran <= nt):
        raise FdRefusal(FdRefusalCode.INVALID_GRID)
    if spot <= 0. or strike <= 0. or min(years, q, sigma) < 0. or style is ExerciseStyle.UNKNOWN:
        raise FdRefusal(FdRefusalCode.INPUT_OUT_OF_DOMAIN)
    if sigma == 0.:
        raise FdRefusal(FdRefusalCode.ZERO_VOLATILITY)


def _mesh(sigma: float, sqrt_t: float, years: float, carry: float,
          abs_log_m: float, grid: FdGrid) -> tuple[float, float, float]:
    var = sigma * sigma
    drift = carry - var / 2
    width = max(grid.width_stdevs * sigma * sqrt_t + abs(drift) * years, abs_log_m + sigma * sqrt_t)
    dx = 2 * width / grid.space_nodes
    if not all(map(math.isfinite, (var, drift, dx))) or dx <= 0.:
        raise FdRefusal(FdRefusalCode.NOT_REPRESENTABLE)
    return var, drift, dx

def _march(sign: int, american: bool, spot: float, strike: float, years: float, rate: float,
           q: float, grid: FdGrid, mesh: tuple[float, float, float]) -> float:
    var, drift, dx = mesh
    if var < abs(drift) * dx:
        raise FdRefusal(FdRefusalCode.GRID_NOT_ADMISSIBLE)
    nx, nt, rannacher = grid.space_nodes, grid.time_steps, grid.rannacher_steps
    center = nx // 2
    spots = [spot * math.exp((i - center) * dx) for i in range(nx + 1)]
    if not math.isfinite(spots[-1]) or spots[0] <= 0.:
        raise FdRefusal(FdRefusalCode.NOT_REPRESENTABLE)
    payoff = [max(0., sign * (s - strike)) for s in spots]
    values, multipliers = payoff.copy(), [0.] * (nx + 1)
    log_m = math.log(strike) - math.log(spot)
    cell = round(log_m / dx) + center
    offset = (cell - center) * dx - log_m
    if 0 < cell < nx and abs(offset) < dx / 2:
        w = dx / 2 + sign * offset
        values[cell] = strike * (math.expm1(sign * w) - sign * w) / dx
    alpha, beta = var / (2 * dx * dx), drift / (2 * dx)
    lower, diagonal, upper = alpha - beta, -2 * alpha - rate, alpha + beta
    dt, tau = years / nt, 0.
    forward = [0.] * (nx + 1)
    for count, h, theta in ((2 * rannacher, dt / 2, 1.), (nt - rannacher, dt, .5)):
        if not count:
            continue
        # Thomas: A_i is the inverse pivot and C_i the normalized upper diagonal.
        a, b, c = -theta * h * lower, 1 - theta * h * diagonal, -theta * h * upper
        pivots, uppers = [0.] * nx, [0.] * nx
        for i in range(1, nx):
            pivots[i] = 1 / (b - a * uppers[i - 1])
            uppers[i] = c * pivots[i]
        eh = (1 - theta) * h
        el, ed, eu = eh * lower, 1 + eh * diagonal, eh * upper
        for _ in range(count):
            tau += h
            disc_q, disc_k = math.exp(-q * tau), strike * math.exp(-rate * tau)
            left = max(payoff[0] if american else 0., sign * (spots[0] * disc_q - disc_k))
            right = max(payoff[nx] if american else 0., sign * (spots[nx] * disc_q - disc_k))
            # Old edges belong to the explicit operator; new edges to implicit elimination.
            forward[0] = left
            for i in range(1, nx):
                rhs = el * values[i - 1] + ed * values[i] + eu * values[i + 1] + h * multipliers[i]
                forward[i] = (rhs - a * forward[i - 1]) * pivots[i]
            w = right
            for i in range(nx - 1, 0, -1):
                w = forward[i] - uppers[i] * w
                if american:
                    trial = w - h * multipliers[i]
                    if trial > payoff[i]:
                        values[i], multipliers[i] = trial, 0.
                    else:
                        values[i] = payoff[i]
                        multipliers[i] = max(0., multipliers[i] + (payoff[i] - w) / h)
                else:
                    values[i] = w
            values[0], values[nx] = left, right
    result = values[center]
    if not math.isfinite(result) or result < 0.:
        raise FdRefusal(FdRefusalCode.NOT_REPRESENTABLE)
    return result


def fd_price(*, kind: OptionKind, style: ExerciseStyle, spot: float, strike: float,
             time_years: float, rate_cont: float, dividend_yield: float, sigma: float,
             grid: FdGrid) -> float:
    """Precifica por unidade, ou levanta uma recusa tipada."""
    try:
        _validate(kind, style, spot, strike, time_years, rate_cont, dividend_yield, sigma, grid)
        sign = 1 if kind is OptionKind.CALL else -1
        if time_years == 0.:
            return max(0., sign * (spot - strike))
        mesh = _mesh(sigma, math.sqrt(time_years), time_years, rate_cont - dividend_yield,
                     abs(math.log(spot) - math.log(strike)), grid)
        return _march(sign, style is ExerciseStyle.AMERICAN, spot, strike, time_years, rate_cont,
                      dividend_yield, grid, mesh)
    except AttributeError as exc:
        raise FdRefusal(FdRefusalCode.INVALID_GRID) from exc
    except (ArithmeticError, MemoryError, ValueError) as exc:
        raise FdRefusal(FdRefusalCode.NOT_REPRESENTABLE) from exc


def fd_implied_vol(*, kind: OptionKind, spot: float, strike: float, time_years: float,
                   rate_cont: float, dividend_yield: float, target_price: float,
                   grid: FdGrid, bracket_lo: float, bracket_hi: float, max_iterations: int,
                   tol_price_rel: float, tol_vol: float, lower_bound: float,
                   price_tick: float) -> FdIvResult:
    """Inverte somente o preço deste motor na malha informada, com recusa sem sigma."""
    floats = (target_price, bracket_lo, bracket_hi, tol_price_rel, tol_vol, lower_bound, price_tick)
    if (any(type(x) is not float or not math.isfinite(x) for x in floats)
            or type(max_iterations) is not int or not 1 <= max_iterations <= 64
            or target_price < 0. or not 0. < bracket_lo < bracket_hi
            or lower_bound < 0. or price_tick <= 0.
            or tol_price_rel <= 0. or tol_vol <= 0.):
        return FdIvResult("invalid_input", None)
    try:
        _validate(kind, ExerciseStyle.AMERICAN, spot, strike, time_years, rate_cont,
                  dividend_yield, bracket_lo, grid)
        if time_years == 0.:
            return FdIvResult("invalid_input", None)
        sign = 1 if kind is OptionKind.CALL else -1
        tol = tol_price_rel * max(1., target_price)
        lower = max(lower_bound, sign * (spot - strike))
        if lower - target_price > tol:
            return FdIvResult("below_intrinsic", None)
        if target_price - lower <= tol or target_price <= lower + price_tick:
            return FdIvResult("not_identifiable", None)
        mesh_inputs = (math.sqrt(time_years), time_years, rate_cont - dividend_yield,
                       abs(math.log(spot) - math.log(strike)), grid)

        def admissible(sigma: float) -> bool:
            var, drift, dx = _mesh(sigma, *mesh_inputs)
            return var >= abs(drift) * dx

        def price(sigma: float) -> float:
            return fd_price(kind=kind, style=ExerciseStyle.AMERICAN, spot=spot, strike=strike,
                            time_years=time_years, rate_cont=rate_cont, sigma=sigma, grid=grid,
                            dividend_yield=dividend_yield)
        lo, hi = bracket_lo, bracket_hi
        if not admissible(hi):
            return FdIvResult("grid_not_admissible", None)
        if not admissible(lo):
            # Admissible sigma form an interval; find its left edge without PDE solves.
            for _ in range(64):
                mid = lo + (hi - lo) / 2
                if mid in (lo, hi):
                    break
                if admissible(mid):
                    hi = mid
                else:
                    lo = mid
            lo, hi = hi, bracket_hi
        floor = lo
        low_price, high_price = price(lo), price(hi)
        if abs(low_price - target_price) <= tol or abs(high_price - target_price) <= tol:
            return FdIvResult("not_identifiable", None)
        if not low_price < target_price < high_price:
            return FdIvResult("unbracketed", None)
        for iteration in range(1, max_iterations + 1):
            sigma = lo + (hi - lo) / 2
            residual = price(sigma) - target_price
            lo, hi = (lo, sigma) if residual > 0. else (sigma, hi)
            if hi - lo <= tol_vol and abs(residual) <= tol:
                left, right = sigma - 1e-6, sigma + 1e-6
                if (left < floor or right > bracket_hi or target_price - price(left) <= tol
                        or price(right) - target_price <= tol):
                    return FdIvResult("not_identifiable", None, iteration)
                return FdIvResult("ok", sigma, iteration)
        return FdIvResult("no_convergence", None, max_iterations)
    except FdRefusal as exc:
        if exc.code is FdRefusalCode.GRID_NOT_ADMISSIBLE:
            return FdIvResult("grid_not_admissible", None)
    except (ArithmeticError, AttributeError, MemoryError, ValueError):
        pass
    return FdIvResult("invalid_input", None)
