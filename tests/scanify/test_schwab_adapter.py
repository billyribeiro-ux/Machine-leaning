"""
Tests for SchwabAdapter — OAuth URL/handshake shape and data parsing.

These use mocks/explicit credentials so they run with no real Schwab account
and never hit the network.
"""
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse, parse_qs

import pytest

from src.scanify.schwab_adapter import SchwabAdapter


def _adapter():
    return SchwabAdapter(client_id="CID", client_secret="SECRET",
                         redirect_uri="https://127.0.0.1", refresh_token="RT")


def test_authorization_url_is_well_formed():
    a = _adapter()
    url = a.get_authorization_url()
    p = urlparse(url)
    assert p.scheme == "https" and p.netloc == "api.schwabapi.com"
    assert p.path == "/v1/oauth/authorize"
    q = parse_qs(p.query)
    assert q["client_id"] == ["CID"]
    assert q["redirect_uri"] == ["https://127.0.0.1"]


def test_is_configured_and_has_refresh_token():
    a = _adapter()
    assert a.is_configured is True
    assert a.has_refresh_token is True
    bare = SchwabAdapter(client_id="", client_secret="")
    assert bare.is_configured is False


def test_exchange_authorization_code_request_shape():
    a = _adapter()
    fake = MagicMock()
    fake.json.return_value = {"access_token": "AT", "refresh_token": "NEWRT", "expires_in": 1800}
    fake.raise_for_status.return_value = None
    with patch("src.scanify.schwab_adapter.requests.post", return_value=fake) as post:
        tok = a.exchange_authorization_code("AUTHCODE")
    assert tok["refresh_token"] == "NEWRT"
    args, kwargs = post.call_args
    assert args[0] == "https://api.schwabapi.com/v1/oauth/token"
    # OAuth: Basic auth header + authorization_code grant
    assert kwargs["headers"]["Authorization"].startswith("Basic ")
    assert kwargs["data"]["grant_type"] == "authorization_code"
    assert kwargs["data"]["code"] == "AUTHCODE"
    # access token now cached
    assert a._access_token == "AT"


def test_get_historical_daily_parses_candles():
    a = _adapter()
    payload = {"candles": [
        {"datetime": 1704067200000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1000},
        {"datetime": 1704153600000, "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 2000},
    ]}
    with patch.object(SchwabAdapter, "_get", return_value=payload):
        bars = a.get_historical_daily("SPY")
    assert len(bars) == 2
    assert set(bars[0]) == {"date", "open", "high", "low", "close", "volume"}
    assert bars[1]["close"] == 2.0 and bars[1]["volume"] == 2000
    assert bars[0]["date"].count("-") == 2          # YYYY-MM-DD


def test_get_historical_daily_handles_errors():
    a = _adapter()
    with patch.object(SchwabAdapter, "_get", side_effect=RuntimeError("boom")):
        assert a.get_historical_daily("SPY") == []
