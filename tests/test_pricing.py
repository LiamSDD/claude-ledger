import json

import pytest

from claude_ledger.pricing import PriceError, Rate, cost, load_prices
from claude_ledger.transcripts import Usage


def test_default_table_has_published_rates():
    table = load_prices()
    opus = table.lookup("claude-opus-5-5")
    assert (opus.input, opus.output, opus.cache_read) == (4.0, 20.0, 0.20)
    assert opus.cache_write_5m == pytest.approx(5.0)
    assert opus.cache_write_1h == pytest.approx(8.0)
    sonnet = table.lookup("claude-sonnet-5-5")
    assert (sonnet.input, sonnet.output, sonnet.cache_read) == (2.0, 10.0, 0.10)
    haiku = table.lookup("claude-haiku-5-5")
    assert (haiku.input, haiku.output, haiku.cache_read) == (0.10, 0.50, 0.01)
    fable = table.lookup("claude-fable-5-2")
    assert (fable.input, fable.output, fable.cache_read) == (8.0, 40.0, 0.20)


@pytest.mark.parametrize(
    "model, expected",
    [
        ("claude-opus-5-5-20261101", "claude-opus-5-5"),
        ("claude-opus-4-7", "claude-opus-5-5"),
        ("claude-3-5-sonnet-20241022", "claude-sonnet-5-5"),
        ("claude-sonnet-4-6", "claude-sonnet-5-5"),
        ("claude-haiku-4-5-20251001", "claude-haiku-5-5"),
        ("us.anthropic.claude-opus-4-1-v1:0", "claude-opus-5-5"),
        ("claude-fable-5-2[1m]", "claude-fable-5-2"),
    ],
)
def test_dated_and_older_ids_fall_back_to_family(model, expected):
    table = load_prices()
    assert table.resolve(model) == expected


@pytest.mark.parametrize("model", ["mystery-model-1", "gpt-5", "", "unknown", "<synthetic>"])
def test_unknown_models_are_not_priced(model):
    assert load_prices().lookup(model) is None


def test_cost_uses_cache_multipliers():
    rate = Rate(input=4.0, output=20.0, cache_read=0.2, cache_write_5m=5.0, cache_write_1h=8.0)
    usage = Usage(input=1_000_000, output=1_000_000, cache_read=1_000_000, cache_write_5m=1_000_000, cache_write_1h=1_000_000)
    assert cost(usage, rate) == pytest.approx(4 + 20 + 0.2 + 5 + 8)


def test_override_file_replaces_and_adds_models(tmp_path):
    override = tmp_path / "prices.json"
    override.write_text(json.dumps({"models": {"claude-opus-5-5": {"input": 1, "output": 2, "cache_read": 0.5}, "acme-1": {"input": 3, "output": 6}}}))
    table = load_prices(str(override))
    opus = table.lookup("claude-opus-5-5-20261101")
    assert (opus.input, opus.output, opus.cache_read, opus.cache_write_5m) == (1, 2, 0.5, 1.25)
    acme = table.lookup("acme-1")
    assert acme.cache_read == pytest.approx(0.3)
    assert table.lookup("claude-haiku-5-5").input == 0.10


def test_override_accepts_flat_model_map(tmp_path):
    override = tmp_path / "flat.json"
    override.write_text(json.dumps({"mystery-model-1": {"input": 1, "output": 1}}))
    assert load_prices(str(override)).lookup("mystery-model-1").output == 1


def test_explicit_cache_write_prices_win(tmp_path):
    override = tmp_path / "p.json"
    override.write_text(json.dumps({"models": {"m-1": {"input": 1, "output": 1, "cache_write_5m": 9, "cache_write_1h": 11}}}))
    rate = load_prices(str(override)).lookup("m-1")
    assert (rate.cache_write_5m, rate.cache_write_1h) == (9, 11)


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '{"models": {"x": {"output": 1}}}', '{"models": {"x": {"input": "a", "output": 1}}}'])
def test_bad_override_raises_price_error(tmp_path, content):
    override = tmp_path / "bad.json"
    override.write_text(content)
    with pytest.raises(PriceError):
        load_prices(str(override))


def test_missing_override_raises_price_error(tmp_path):
    with pytest.raises(PriceError):
        load_prices(str(tmp_path / "nope.json"))
