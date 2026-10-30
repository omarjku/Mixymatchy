"""Budget guard for the optional LLM 'understand' layer (engine/llm.py).

Owner's hard limit: total LLM spend < EUR 5.  Every call is counted from response.usage (input, output,
cache write, cache read tokens) and priced with the model's list price; calls stop for good once the
estimated spend reaches SECOND_LOOK_LLM_BUDGET_EUR (default 4.0) or today's calls reach
SECOND_LOOK_LLM_MAX_CALLS_PER_DAY (default 3000).

State lives in-process and in a JSON file (SECOND_LOOK_LLM_BUDGET_FILE, default data/llm_budget.json;
data/ is gitignored) so a restart keeps the count.  A redeploy that wipes the disk resets it: keep a spend
limit on the Anthropic workspace as the outer backstop.

Prices are USD per million tokens; USD is counted 1:1 as EUR (over-estimates the euro spend, i.e. errs
on the safe side).  Unknown models are priced at Opus-tier rates for the same reason.
"""
import json
import os
import threading
import time
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# USD per 1M tokens: input, output.  Cache writes (5 min TTL) cost 1.25x input, cache reads 0.1x input.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
UNKNOWN_PRICE = (5.00, 25.00)
CACHE_WRITE_X = 1.25
CACHE_READ_X = 0.10
USD_TO_EUR = 1.0
CACHE_SIZE = 512


def budget_eur():
    return float(os.environ.get("SECOND_LOOK_LLM_BUDGET_EUR", "4.0"))


def max_calls_per_day():
    return int(os.environ.get("SECOND_LOOK_LLM_MAX_CALLS_PER_DAY", "3000"))


def path():
    return os.environ.get("SECOND_LOOK_LLM_BUDGET_FILE", os.path.join(ROOT, "data", "llm_budget.json"))


def cost_eur(model, input_tokens=0, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0):
    pin, pout = PRICES.get(model, UNKNOWN_PRICE)
    usd = (input_tokens * pin + cache_write_tokens * pin * CACHE_WRITE_X + cache_read_tokens * pin * CACHE_READ_X
           + output_tokens * pout) / 1e6
    return usd * USD_TO_EUR


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def _fresh():
    return {"day": _today(), "calls_today": 0, "calls_total": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_write_tokens": 0, "cache_read_tokens": 0, "spend_eur": 0.0, "cache_hits": 0,
            "blocked": 0, "errors": 0}


class Budget:
    def __init__(self, file=None):
        self.file = file or path()
        self.lock = threading.Lock()
        self.state = _fresh()
        self.cache = OrderedDict()
        try:
            with open(self.file, encoding="utf-8") as fh:
                saved = json.load(fh)
            if isinstance(saved, dict):
                self.state.update({k: saved[k] for k in self.state if k in saved})
        except (OSError, ValueError):
            pass

    def _roll_day(self):
        if self.state["day"] != _today():
            self.state["day"], self.state["calls_today"] = _today(), 0

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.file), exist_ok=True)
            tmp = self.file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.state, fh, indent=1)
            os.replace(tmp, self.file)
        except OSError:
            pass  # the in-process counter still applies

    def why_blocked(self):
        """None if a call may go out now, else the reason (budget or daily cap)."""
        with self.lock:
            self._roll_day()
            if self.state["spend_eur"] >= budget_eur():
                return "budget"
            if self.state["calls_today"] >= max_calls_per_day():
                return "daily_cap"
            return None

    def reserve(self):
        """Count a call before it goes out (parallel requests cannot overshoot the daily cap).
        -> True if allowed."""
        with self.lock:
            self._roll_day()
            if self.state["spend_eur"] >= budget_eur() or self.state["calls_today"] >= max_calls_per_day():
                self.state["blocked"] += 1
                return False
            self.state["calls_today"] += 1
            self.state["calls_total"] += 1
            self._save()
            return True

    def record(self, model, usage):
        """Add response.usage to the counters; -> cost of this call in EUR."""
        def n(name):
            return int(getattr(usage, name, 0) or 0)
        tin, tout = n("input_tokens"), n("output_tokens")
        tcw, tcr = n("cache_creation_input_tokens"), n("cache_read_input_tokens")
        eur = cost_eur(model, tin, tout, tcw, tcr)
        with self.lock:
            s = self.state
            s["input_tokens"] += tin
            s["output_tokens"] += tout
            s["cache_write_tokens"] += tcw
            s["cache_read_tokens"] += tcr
            s["spend_eur"] = round(s["spend_eur"] + eur, 8)
            self._save()
        return eur

    def error(self):
        with self.lock:
            self.state["errors"] += 1

    # LRU cache of validated proposals: a repeated situation costs nothing
    def cache_get(self, key):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.state["cache_hits"] += 1
                return self.cache[key]
            return None

    def cache_put(self, key, value):
        with self.lock:
            self.cache[key] = value
            self.cache.move_to_end(key)
            while len(self.cache) > CACHE_SIZE:
                self.cache.popitem(last=False)

    def snapshot(self):
        with self.lock:
            self._roll_day()
            return dict(self.state, budget_eur=budget_eur(), max_calls_per_day=max_calls_per_day())


_BUDGET = None
_BUDGET_LOCK = threading.Lock()


def budget():
    global _BUDGET
    with _BUDGET_LOCK:
        if _BUDGET is None or _BUDGET.file != path():
            _BUDGET = Budget()
        return _BUDGET


def reset(file=None):
    """Tests: start from a fresh budget (optionally on another file)."""
    global _BUDGET
    with _BUDGET_LOCK:
        if file:
            os.environ["SECOND_LOOK_LLM_BUDGET_FILE"] = file
        _BUDGET = Budget()
        return _BUDGET
