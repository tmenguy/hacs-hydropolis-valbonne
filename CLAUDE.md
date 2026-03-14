# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant (HACS) custom component that fetches water meter readings from SPL Hydropolis (water utility for Valbonne / Sophia Antipolis, France) and integrates them into HA's Energy dashboard. Domain: `hydropolis_valbonne`.

## Commands

### Run all tests
```bash
pip install -r requirements_test.txt
pytest
```

### Run a single test file or test
```bash
pytest tests/test_coordinator.py
pytest tests/test_coordinator.py::test_first_refresh_fetches_full_history -v
```

### Run with coverage
```bash
pytest --cov=custom_components/hydropolis_valbonne --cov-report=term-missing
```

### Live API tests (skipped by default)
Create a `.env` file from `.env.example` with real Hydropolis credentials, then:
```bash
pytest tests/test_api.py -v
```

## Architecture

### Three-API Authentication Chain

The integration authenticates through three chained JVS-Mairistem APIs:

1. **Omega SSO API** (`omegasso.jvsonline.fr`) — email/password login → JWT token
2. **Omega Main API** (`omegaweb.jvsonline.fr`) — JWT → contract list
3. **3Int Partner API** (`api2.hydropolis-sophia.fr`) — token exchange → daily meter measures

### Core Components (in `custom_components/hydropolis_valbonne/`)

- **`api.py`** — `HydropolisClient`: async HTTP client handling the 3-API auth chain, token caching, auto-reauth on 401, and paginated measure fetching. Parses `data_available_since` from the 3Int JWT claims.
- **`coordinator.py`** — `HydropolisCoordinator`: extends HA's `DataUpdateCoordinator`. On first run, imports full history into HA long-term statistics via `async_add_external_statistics()`. Subsequent refreshes are incremental (fetches only from last recorded statistic onward). Refreshes every 12 hours.
- **`sensor.py`** — `HydropolisWaterMeterSensor`: extends `CoordinatorEntity` + `RestoreEntity`. Shows current meter total in liters. **Intentionally has no `state_class`** to prevent HA from auto-generating statistics that would conflict with the external statistics.
- **`config_flow.py`** — Two-step setup: credentials → contract selection (if multiple).

### Data Flow

```
Hydropolis APIs → HydropolisClient.get_daily_measures()
    → HydropolisCoordinator._async_update_data()
        → _import_statistics() → async_add_external_statistics() (recorder DB)
        → HydropolisData → HydropolisWaterMeterSensor (entity state)
```

### Critical Design Decisions

- **External statistics, not state_class**: Data arrives in delayed daily batches (2-5 day lag), so HA's auto-statistics would be inaccurate. External statistics (`hydropolis_valbonne:<contrat_id>_water_meter`) are imported directly.
- **Incremental fetching**: Full history on first run (back to `data_available_since` or 4 years), delta-only afterward by checking last recorded statistic timestamp.
- **RestoreEntity**: Persists last meter value + measurement timestamp across HA restarts via `ExtraStoredData`.
- **recorder dependency**: The integration depends on the `recorder` component (declared in `manifest.json`).

## Testing

Tests use `pytest-homeassistant-custom-component` which provides the `hass` fixture, `MockConfigEntry`, recorder support, etc. All tests are async (`asyncio_mode = auto`).

Fixtures in `tests/conftest.py` provide `mock_hydropolis_client` (patches both `coordinator` and `config_flow` modules), `fake_contract`, `fake_measures`, and `mock_config_entry`.

## Specification

`SPECIFICATION.md` contains the full reverse-engineered API documentation, authentication flow details, data model, and design rationale. Consult it when modifying API interactions or statistics handling.
