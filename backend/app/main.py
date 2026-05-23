from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import load_config
from .data_provider import get_provider
from .backtest import run_full_backtest
from .experiments import run_mvb
from .strategy import build_dashboard, build_series
from .trial import build_trial_run


class SimulateRequest(BaseModel):
    date: str | None = None
    sector: str | None = None
    overrides: dict[str, Any] | None = None


app = FastAPI(title="行业趋势确认型智能定投系统 MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _provider_and_config(overrides: dict[str, Any] | None = None):
    config = load_config(overrides)
    provider = get_provider(config["data_source"], config)
    return provider, config


def _config_key(config: dict[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, sort_keys=True)


def _public_dashboard(dashboard: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dashboard.items() if key != "timeline"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


@lru_cache(maxsize=32)
def _cached_dashboard(config_key: str, date: str | None) -> dict[str, Any]:
    config = json.loads(config_key)
    provider = get_provider(config["data_source"], config)
    return build_dashboard(provider.frame(), config, date)


@lru_cache(maxsize=16)
def _cached_mvb(config_key: str) -> dict[str, Any]:
    config = json.loads(config_key)
    provider = get_provider(config["data_source"], config)
    return run_mvb(provider.frame(), config)


@lru_cache(maxsize=16)
def _cached_backtest(config_key: str) -> dict[str, Any]:
    config = json.loads(config_key)
    provider = get_provider(config["data_source"], config)
    return run_full_backtest(provider.frame(), config)


@lru_cache(maxsize=16)
def _cached_trial_run(config_key: str, mode: str) -> dict[str, Any]:
    config = json.loads(config_key)
    provider = get_provider(config["data_source"], config)
    return build_trial_run(provider.frame(), config, mode=mode)


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    provider, config = _provider_and_config()
    return {
        "config": config,
        "sectors": provider.sectors(),
        "benchmark": config["benchmark"],
        "latest_date": provider.latest_date(),
        "data_source": config["data_source"],
    }


@app.get("/api/data-audit")
def get_data_audit() -> dict[str, Any]:
    provider, config = _provider_and_config()
    return {"data_source": config["data_source"], "audit": provider.audit()}


@app.get("/api/mvb")
def get_mvb() -> dict[str, Any]:
    provider, config = _provider_and_config()
    return _json_safe(_cached_mvb(_config_key(config)))


@app.get("/api/backtest")
def get_backtest() -> dict[str, Any]:
    provider, config = _provider_and_config()
    return _json_safe(_cached_backtest(_config_key(config)))


@app.get("/api/trial-run")
def get_trial_run(mode: str = Query(default="paper")) -> dict[str, Any]:
    provider, config = _provider_and_config()
    return _json_safe(_cached_trial_run(_config_key(config), mode))


@app.get("/api/dashboard")
def get_dashboard(date: str | None = Query(default=None)) -> dict[str, Any]:
    provider, config = _provider_and_config()
    return _public_dashboard(_cached_dashboard(_config_key(config), date))


@app.get("/api/series")
def get_series(sector: str = Query(...), date: str | None = Query(default=None)) -> dict[str, Any]:
    provider, config = _provider_and_config()
    try:
        dashboard = _cached_dashboard(_config_key(config), date)
        if sector not in dashboard["timeline"]:
            raise KeyError(sector)
        return {
            "sector": sector,
            "date": dashboard["date"],
            "points": dashboard["timeline"][sector],
            "exit_state": next((item for item in dashboard["exit_states"] if item["sector"] == sector), None),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown sector: {sector}") from exc


@app.post("/api/simulate")
def simulate(request: SimulateRequest) -> dict[str, Any]:
    provider, config = _provider_and_config(request.overrides)
    dashboard = _cached_dashboard(_config_key(config), request.date)
    selected_sector = request.sector or (dashboard["signals"][0]["sector"] if dashboard["signals"] else config["sectors"][0])
    series = {
        "sector": selected_sector,
        "date": dashboard["date"],
        "points": dashboard["timeline"][selected_sector],
        "exit_state": next((item for item in dashboard["exit_states"] if item["sector"] == selected_sector), None),
    }
    return {"dashboard": _public_dashboard(dashboard), "series": series, "config": config}
