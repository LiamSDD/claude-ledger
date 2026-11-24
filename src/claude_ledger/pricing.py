from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .transcripts import Usage

MTOK = 1_000_000
BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices.json")


class PriceError(Exception):
    pass


@dataclass(frozen=True)
class Rate:
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


@dataclass
class Multipliers:
    cache_write_5m: float = 1.25
    cache_write_1h: float = 2.0
    cache_read: float = 0.1


class PriceTable:
    def __init__(self, models: Dict[str, Rate], families: Dict[str, str]):
        self.models = models
        self.families = families
        self._cache: Dict[str, Optional[str]] = {}

    def resolve(self, model: str) -> Optional[str]:
        if model in self._cache:
            return self._cache[model]
        found = self._resolve(model)
        self._cache[model] = found
        return found

    def _resolve(self, model: str) -> Optional[str]:
        if not model:
            return None
        if model in self.models:
            return model
        prefixed = [key for key in self.models if model.startswith(key)]
        if prefixed:
            return max(prefixed, key=len)
        words = set(re.split(r"[^a-z0-9]+", model.lower()))
        for family, target in self.families.items():
            if family.lower() in words and target in self.models:
                return target
        return None

    def lookup(self, model: str) -> Optional[Rate]:
        key = self.resolve(model)
        return self.models[key] if key else None

    def family_rate(self, family: str) -> Optional[Rate]:
        target = self.families.get(family)
        return self.models.get(target) if target else None


def cost(usage: Usage, rate: Rate) -> float:
    return (
        usage.input * rate.input
        + usage.output * rate.output
        + usage.cache_read * rate.cache_read
        + usage.cache_write_5m * rate.cache_write_5m
        + usage.cache_write_1h * rate.cache_write_1h
    ) / MTOK


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise PriceError(f"{where} must be a non-negative number")
    return float(value)


def _rate(name: str, raw: Any, mult: Multipliers) -> Rate:
    if not isinstance(raw, dict):
        raise PriceError(f"price for {name} must be an object")
    for required in ("input", "output"):
        if required not in raw:
            raise PriceError(f"price for {name} is missing '{required}'")
    inp = _number(raw["input"], f"{name}.input")
    out = _number(raw["output"], f"{name}.output")

    def pick(key: str, default: float) -> float:
        return _number(raw[key], f"{name}.{key}") if key in raw else default

    return Rate(
        input=inp,
        output=out,
        cache_read=pick("cache_read", inp * mult.cache_read),
        cache_write_5m=pick("cache_write_5m", inp * mult.cache_write_5m),
        cache_write_1h=pick("cache_write_1h", inp * mult.cache_write_1h),
    )


def _read(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise PriceError(f"cannot read prices file {path}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise PriceError(f"prices file {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PriceError(f"prices file {path} must contain a JSON object")
    return data


def _apply(data: Dict[str, Any], raw_models: Dict[str, Any], families: Dict[str, str], mult: Multipliers) -> None:
    for key, attr in (("cache_write_5m_multiplier", "cache_write_5m"), ("cache_write_1h_multiplier", "cache_write_1h"), ("cache_read_multiplier", "cache_read")):
        if key in data:
            setattr(mult, attr, _number(data[key], key))
    models = data.get("models") if "models" in data else {k: v for k, v in data.items() if isinstance(v, dict) and k != "families"}
    if not isinstance(models, dict):
        raise PriceError("'models' must be an object")
    raw_models.update(models)
    fams = data.get("families", {})
    if not isinstance(fams, dict) or not all(isinstance(v, str) for v in fams.values()):
        raise PriceError("'families' must map family names to model ids")
    families.update(fams)


def load_prices(path: Optional[str] = None) -> PriceTable:
    raw_models: Dict[str, Any] = {}
    families: Dict[str, str] = {}
    mult = Multipliers()
    _apply(_read(BUNDLED), raw_models, families, mult)
    if path:
        _apply(_read(path), raw_models, families, mult)
    models = {name: _rate(name, raw, mult) for name, raw in raw_models.items()}
    return PriceTable(models, families)
