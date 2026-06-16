# SCANIFY Scanner Audit — 2026-06-13

Audit of the 0DTE SPX options + GEX scanner modules under `src/scanify/`,
performed alongside the FMP equity integration and dependency refresh.

## Fixed in this pass

| Sev | Module | Finding | Resolution |
|-----|--------|---------|------------|
| **P0** | `gex_engine.py` | `_time_to_expiry()` read `chain.expiry`, but `OptionsChain` exposes `expiry_date` (a `date`). Every GEX cycle raised `AttributeError`. | Use `expiry_date` anchored to 16:00 ET (20:00 UTC) PM settlement to build a tz-aware expiry instant. |
| **P0** | `gex_engine.py` | Newton-Raphson IV solver `break`s on vega collapse (deep-OTM / near-expiry 0DTE) and returned a possibly-stale `sigma`, inflating GEX. | Added bracketed `_iv_bisection()` fallback invoked on vega collapse and on non-convergence. Verified exact round-trip (0.18→0.18) for normal strikes. |
| **P1** | `premium_seller.py` / `config.py` | Nearest-quote search hard-rejected strikes >10 pts from target, dropping valid spreads on wide/illiquid chains. | New `PremiumSellConfig.max_strike_distance` (default 15.0) threaded through all four call sites. |
| **P1** | `equity_*.py` (API) | Equity endpoints still sourced data from Yahoo after FMP was designated the equity vendor. | Price/macro/internals/session endpoints now use `FMPAdapter`; new `/api/equity/market` router for FMP-only features. |
| **—** | `requirements.txt` / `pyproject.toml` | `requests` and `cryptography` used by the FMP/EDGAR adapters and credential store but undeclared. | Added with pinned floors. |

## Reviewed — no change required (audit false-positives)

- `data_feeds.get_vwap()` and `premium_seller._compute_vwap()` already check
  `total_volume == 0` **before** the division — no NaN risk.
- `directional.py` already guards `if vwap <= 0: return None` before scoring.
- `market_internals` A/D scoring initialises `ad_score = 0.0`; the "missing else"
  is the intended neutral default, not a bug.

## Open items (tracked, not yet addressed)

- **P1** `orchestrator.run_scan_cycle()` has no try/except around
  `gex_engine.compute_gex()` — a single corrupt chain snapshot aborts the cycle.
  Recommend wrapping and falling back to the prior GEX snapshot.
- **P1** `orchestrator` does not enforce `risk.max_concurrent_positions` before
  emitting new signals.
- **P2** `exit_manager` break-even logic covers long options only; credit
  spreads should floor on the long-leg debit.
- **P2** `credentials._default_master_key()` derives from `platform.node()` —
  acceptable for dev, but production should require `SCANIFY_MASTER_KEY`.
