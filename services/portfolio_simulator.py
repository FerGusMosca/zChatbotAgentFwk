# services/portfolio_simulator.py
#
# Backtests a portfolio over a date range under one trading rule.
#
# The rule available today is the moving average filter: hold a position while
# its close sits above its own N-day moving average, sit in cash while it does
# not. N defaults to 200.
#
# Two decisions worth knowing about, because they are what separates a backtest
# from a number that looks good and cannot be traded:
#
#   1. The signal is acted on the FOLLOWING day. Reading today's close and
#      pretending you traded at today's close is looking at the future.
#
#   2. Prices are pulled from BEFORE the start date so the average is already
#      warmed up on day one. Without that, the first N days of any simulation
#      have no signal and silently default to being invested.

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

MAX_SYMBOLS = 40
DEFAULT_MA_WINDOW = 200


class SimulationError(Exception):
    """Raised when the simulation cannot run at all (bad input, no data)."""


# ─────────────────────────────────────────────────────────────────────────────
# Input parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_symbols(raw):
    """Accepts 'AAPL, MSFT\nNVDA' or a list. Returns a de-duplicated list."""
    if isinstance(raw, (list, tuple)):
        candidates = list(raw)
    else:
        candidates = str(raw or "").replace("\n", ",").replace(";", ",").split(",")

    symbols = []
    for candidate in candidates:
        symbol = str(candidate).strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise SimulationError("No symbols to simulate.")

    if len(symbols) > MAX_SYMBOLS:
        raise SimulationError(
            f"{len(symbols)} symbols is too many for one run (limit is {MAX_SYMBOLS}). "
            f"Each one is a separate download.")

    return symbols


def resolve_weights(symbols, mode, raw_weights=None):
    """
    Returns {symbol: weight} summing to 1.

    mode 'equal'    → every symbol gets the same share.
    mode 'relative' → the caller passes relative numbers (3, 2, 1 or 50, 30, 20);
                      they are normalised here, so they need not add up to
                      anything in particular.
    """
    if mode != "relative":
        share = 1.0 / len(symbols)
        return {symbol: share for symbol in symbols}

    raw_weights = raw_weights or {}
    values = {}

    for symbol in symbols:
        try:
            value = float(raw_weights.get(symbol, 0) or 0)
        except (TypeError, ValueError):
            raise SimulationError(f"Weight for {symbol} is not a number.")

        if value < 0:
            raise SimulationError(f"Weight for {symbol} is negative.")

        values[symbol] = value

    total = sum(values.values())
    if total <= 0:
        raise SimulationError("The weights add up to zero: nothing would be invested.")

    return {symbol: value / total for symbol, value in values.items()}


def parse_date(value, label):
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        raise SimulationError(f"{label} must look like 2024-01-31.")


# ─────────────────────────────────────────────────────────────────────────────
# Price download
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_history(client, symbol, period1, period2):
    """Daily closes for one symbol. Returns [(date_string, close), ...]."""
    url = YAHOO_CHART.format(symbol=symbol)
    params = {
        "interval": "1d",
        "period1": int(period1.timestamp()),
        "period2": int(period2.timestamp()),
        "events": "div,split",
    }

    resp = await client.get(url, params=params, headers=HEADERS)
    if resp.status_code != 200:
        return symbol, None, f"price provider answered {resp.status_code}"

    payload = resp.json()
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return symbol, None, "no price history returned"

    result = results[0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    # Adjusted closes are what a backtest needs: splits and dividends already
    # folded in. They are not always present, so the raw close is the fallback.
    adjusted = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]
                .get("adjclose"))
    series_values = adjusted if adjusted and len(adjusted) == len(stamps) else closes

    series = []
    for stamp, value in zip(stamps, series_values):
        if value is None:
            continue  # holidays and halts come back as nulls
        day = datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d")
        series.append((day, float(value)))

    if not series:
        return symbol, None, "price history came back empty"

    return symbol, series, None


async def fetch_all(symbols, period1, period2):
    """Downloads every symbol at once. Returns (histories, failures)."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        tasks = [_fetch_history(client, symbol, period1, period2) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    histories = {}
    failures = {}

    for symbol, outcome in zip(symbols, results):
        if isinstance(outcome, Exception):
            failures[symbol] = f"{type(outcome).__name__}: {outcome}"
            continue

        _, series, error = outcome
        if error:
            failures[symbol] = error
        else:
            histories[symbol] = series

    return histories, failures


# ─────────────────────────────────────────────────────────────────────────────
# The simulation itself
# ─────────────────────────────────────────────────────────────────────────────

def moving_average_signals(series, window):
    """
    For each day, says whether the close was above its own moving average.

    Returns {date: True/False}. Days before the average has enough history are
    left out entirely rather than guessed.
    """
    signals = {}
    running = 0.0
    values = []

    for day, close in series:
        values.append(close)
        running += close

        if len(values) > window:
            running -= values[-window - 1]

        if len(values) >= window:
            average = running / window
            signals[day] = close > average

    return signals


def simulate(histories, weights, start, end, ma_window):
    """
    Walks the calendar day by day and grows each sleeve of the portfolio.

    Each symbol is its own sleeve: it earns its daily return while its signal
    says invested, and earns nothing while it says cash. Weights are set once
    at the start and left alone — no rebalancing — so what comes out is the
    rule's contribution, not a rebalancing effect on top of it.
    """
    start_day = start.strftime("%Y-%m-%d")
    end_day = end.strftime("%Y-%m-%d")

    # Every trading day any symbol saw inside the window
    calendar = sorted({
        day
        for series in histories.values()
        for day, _ in series
        if start_day <= day <= end_day
    })

    if len(calendar) < 2:
        raise SimulationError(
            "The date range holds fewer than two trading days of data.")

    prices = {symbol: dict(series) for symbol, series in histories.items()}
    signals = {symbol: moving_average_signals(series, ma_window)
               for symbol, series in histories.items()}

    # Sleeve value and buy-and-hold value, both starting at their weight
    sleeves = {symbol: weight for symbol, weight in weights.items()}
    holds = {symbol: weight for symbol, weight in weights.items()}

    # Yesterday's signal is what can be traded today
    invested = {symbol: False for symbol in weights}
    last_price = {}
    days_invested = {symbol: 0 for symbol in weights}
    switches = {symbol: 0 for symbol in weights}
    missing_signal = set()

    curve = []
    peak = 1.0
    max_drawdown = 0.0
    drawdown_day = None

    for day in calendar:
        for symbol in weights:
            price = prices[symbol].get(day)
            if price is None:
                continue  # symbol did not trade that day

            previous = last_price.get(symbol)
            if previous:
                daily_return = price / previous - 1.0
                holds[symbol] *= (1.0 + daily_return)
                if invested[symbol]:
                    sleeves[symbol] *= (1.0 + daily_return)
                    days_invested[symbol] += 1

            last_price[symbol] = price

            # Today's close decides tomorrow's position
            signal = signals[symbol].get(day)
            if signal is None:
                missing_signal.add(symbol)
            elif signal != invested[symbol]:
                invested[symbol] = signal
                switches[symbol] += 1

        value = sum(sleeves.values())
        hold_value = sum(holds.values())
        curve.append({"date": day, "strategy": round(value, 6),
                      "buy_hold": round(hold_value, 6)})

        peak = max(peak, value)
        drawdown = value / peak - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            drawdown_day = day

    final = sum(sleeves.values())
    final_hold = sum(holds.values())

    # Buy and hold drawdown, for the same window
    hold_peak = 1.0
    hold_max_drawdown = 0.0
    for point in curve:
        hold_peak = max(hold_peak, point["buy_hold"])
        hold_max_drawdown = min(hold_max_drawdown, point["buy_hold"] / hold_peak - 1.0)

    total_days = len(calendar)
    years = total_days / 252.0

    per_symbol = []
    for symbol in sorted(weights, key=lambda s: -weights[s]):
        per_symbol.append({
            "symbol": symbol,
            "weight": round(weights[symbol], 6),
            "strategy_return": round(sleeves[symbol] / weights[symbol] - 1.0, 6)
                               if weights[symbol] else 0.0,
            "buy_hold_return": round(holds[symbol] / weights[symbol] - 1.0, 6)
                               if weights[symbol] else 0.0,
            "days_invested": days_invested[symbol],
            "time_invested": round(days_invested[symbol] / total_days, 4) if total_days else 0.0,
            "switches": switches[symbol],
        })

    return {
        "from": calendar[0],
        "to": calendar[-1],
        "trading_days": total_days,
        "ma_window": ma_window,
        "strategy": {
            "total_return": round(final - 1.0, 6),
            "annualized_return": round(final ** (1 / years) - 1.0, 6) if years > 0 and final > 0 else None,
            "max_drawdown": round(max_drawdown, 6),
            "max_drawdown_date": drawdown_day,
        },
        "buy_hold": {
            "total_return": round(final_hold - 1.0, 6),
            "annualized_return": round(final_hold ** (1 / years) - 1.0, 6) if years > 0 and final_hold > 0 else None,
            "max_drawdown": round(hold_max_drawdown, 6),
        },
        "per_symbol": per_symbol,
        "curve": curve,
        "symbols_without_signal": sorted(missing_signal),
    }


async def run_simulation(symbols, weight_mode, raw_weights,
                         start_date, end_date, ma_window=DEFAULT_MA_WINDOW):
    """Entry point: parses, downloads and simulates."""
    symbols = parse_symbols(symbols)
    weights = resolve_weights(symbols, weight_mode, raw_weights)

    start = parse_date(start_date, "The start date")
    end = parse_date(end_date, "The end date")

    if end <= start:
        raise SimulationError("The end date must come after the start date.")

    try:
        ma_window = int(ma_window or DEFAULT_MA_WINDOW)
    except (TypeError, ValueError):
        raise SimulationError("The moving average window must be a whole number.")

    if ma_window < 2:
        raise SimulationError("A moving average shorter than 2 days is not a moving average.")

    # Warm-up: enough calendar days back to fill the average before day one.
    # Markets trade about 252 days a year, so the window is padded generously
    # and the extra data is simply ignored by the simulation.
    warmup_days = int(ma_window * 1.6) + 15
    period1 = start - timedelta(days=warmup_days)

    histories, failures = await fetch_all(symbols, period1, end + timedelta(days=2))

    if not histories:
        raise SimulationError(
            "No price history came back for any symbol. "
            + "; ".join(f"{s}: {m}" for s, m in failures.items()))

    # Symbols that failed are dropped and their weight redistributed, so the
    # run still means something instead of silently holding phantom cash.
    if failures:
        weights = {s: w for s, w in weights.items() if s in histories}
        total = sum(weights.values())
        weights = {s: w / total for s, w in weights.items()}

    result = simulate(histories, weights, start, end, ma_window)
    result["failures"] = failures
    result["weight_mode"] = weight_mode
    return result
