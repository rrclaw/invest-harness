import pytest
from unittest.mock import patch, MagicMock
from adapters.adapter_polymarket import PolymarketAdapter
from adapters.market_data import Quote


@pytest.fixture
def adapter():
    return PolymarketAdapter(api_url="https://gamma-api.polymarket.com")


def test_get_quote(adapter):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "0x123",
        "question": "Will X happen?",
        "outcomePrices": [0.65, 0.35],
        "volume": 1500000,
        "slug": "will-x-happen",
    }
    with patch("adapters.adapter_polymarket.requests.get", return_value=mock_response):
        quote = adapter.get_quote("will-x-happen")
    assert isinstance(quote, Quote)
    assert quote.ticker == "will-x-happen"
    assert quote.price == 0.65
    assert quote.volume == 1500000
    assert quote.extra["question"] == "Will X happen?"
    assert quote.extra["no_price"] == 0.35


def test_get_quotes(adapter):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "id": "0x123",
            "question": "Q1?",
            "outcomePrices": [0.65, 0.35],
            "volume": 100000,
            "slug": "q1",
        },
        {
            "id": "0x456",
            "question": "Q2?",
            "outcomePrices": [0.40, 0.60],
            "volume": 200000,
            "slug": "q2",
        },
    ]
    with patch("adapters.adapter_polymarket.requests.get", return_value=mock_response):
        quotes = adapter.get_quotes(["q1", "q2"])
    assert len(quotes) == 2


def test_get_daily_bars_not_applicable(adapter):
    """Polymarket has no OHLC bars -- returns empty list."""
    bars = adapter.get_daily_bars("slug", "2026-03-25", "2026-03-26")
    assert bars == []


def test_health_check_success(adapter):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    with patch("adapters.adapter_polymarket.requests.get", return_value=mock_response):
        assert adapter.health_check() is True


def test_health_check_failure(adapter):
    with patch("adapters.adapter_polymarket.requests.get", side_effect=Exception("timeout")):
        assert adapter.health_check() is False


def test_odds_slope_calculation(adapter):
    """Test odds slope detection: >10% change in 60 min."""
    old_price = 0.50
    new_price = 0.62  # 12% absolute change
    slope = adapter.calculate_odds_slope(old_price, new_price)
    assert slope == pytest.approx(12.0)


def test_odds_slope_below_threshold(adapter):
    old_price = 0.50
    new_price = 0.53  # 3% change
    slope = adapter.calculate_odds_slope(old_price, new_price)
    assert slope == pytest.approx(3.0)
