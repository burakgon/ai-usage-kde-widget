import pytest

from ai_usage_kde.usage.pricing import cost_usd, model_family


@pytest.mark.parametrize("name,family", [
    ("claude-opus-4-7", "opus"),
    ("claude-sonnet-4-5", "sonnet"),
    ("claude-3-5-haiku-20241022", "haiku"),
    ("<synthetic>", None),
    ("something-unknown", None),
])
def test_model_family(name, family):
    assert model_family(name) == family


def test_cost_opus_known_values():
    # opus: input 15, output 75, cache_write 18.75, cache_read 1.50 per 1e6 tokens
    c = cost_usd("claude-opus-4-7",
                 input_tokens=1_000_000, output_tokens=1_000_000,
                 cache_creation_input_tokens=1_000_000, cache_read_input_tokens=1_000_000)
    assert c == pytest.approx(15 + 75 + 18.75 + 1.50, rel=1e-9)


def test_cost_unknown_model_is_zero():
    assert cost_usd("<synthetic>", input_tokens=10, output_tokens=10,
                    cache_creation_input_tokens=0, cache_read_input_tokens=0) == 0.0
