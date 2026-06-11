"""Test that pricing data exists for all models in the context window table."""
from src.provider import MODEL_CONTEXT_WINDOWS


def test_pricing_covers_all_known_models():
    """Every model in MODEL_CONTEXT_WINDOWS should have pricing data.
    
    This ensures /cost works for all supported models — not just a subset.
    The _find_model_pricing function uses prefix matching, so we only need
    to check that each model resolves to a pricing entry.
    """
    # Import the pricing finder — it's in repl.py so we test it via import
    from src.repl import _find_model_pricing

    missing = []
    for model in MODEL_CONTEXT_WINDOWS:
        pricing = _find_model_pricing(model)
        if pricing is None:
            missing.append(model)

    assert not missing, (
        f"These models have context window info but no pricing data: {missing}\n"
        f"Add them to _MODEL_PRICING in repl.py so /cost works for all models."
    )


def test_pricing_has_reasonable_values():
    """Pricing should be positive and not unreasonably high."""
    from src.repl import _MODEL_PRICING

    for model, pricing in _MODEL_PRICING.items():
        assert pricing["input"] > 0, f"{model} has zero input price"
        assert pricing["output"] > 0, f"{model} has zero output price"
        # Sanity: no model should cost more than $100/1M tokens
        assert pricing["input"] < 100, f"{model} input price seems too high: ${pricing['input']}"
        assert pricing["output"] < 100, f"{model} output price seems too high: ${pricing['output']}"


def test_new_model_pricing():
    """Verify specific pricing entries for newly added models."""
    from src.repl import _find_model_pricing

    # GPT-4.1 family
    assert _find_model_pricing("gpt-4.1") is not None
    assert _find_model_pricing("gpt-4.1-mini") is not None
    assert _find_model_pricing("gpt-4.1-nano") is not None

    # o-series
    assert _find_model_pricing("o3") is not None
    assert _find_model_pricing("o3-mini") is not None
    assert _find_model_pricing("o4-mini") is not None

    # Claude 4
    assert _find_model_pricing("claude-opus-4") is not None
    assert _find_model_pricing("claude-sonnet-4") is not None

    # Gemini 2.5
    assert _find_model_pricing("gemini-2.5-pro") is not None
    assert _find_model_pricing("gemini-2.5-flash") is not None

    # DeepSeek V3/R1
    assert _find_model_pricing("deepseek-v3") is not None
    assert _find_model_pricing("deepseek-r1") is not None
