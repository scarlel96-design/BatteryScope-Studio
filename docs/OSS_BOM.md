# OSS bill of materials (uv.lock)

Resolver-locked graph: **50 packages** across supported platform markers. Direct dependencies below are version-matched to `uv.lock`; optional device libraries are not part of the default runtime install. The full graph is in `SBOM.spdx.json`.

| Name | Version | Purpose | License | Repository | Scope | Reason selected | Alternative |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pydantic | 2.13.5 | typed configuration and sample validation | MIT | https://pypi.org/pypi/pydantic/2.13.5/json | Runtime | strict models | attrs |
| pyarrow | 24.0.0 | Arrow and ZSTD Parquet raw chunks | Apache-2.0 | https://pypi.org/pypi/pyarrow/24.0.0/json | Runtime | columnar raw persistence | parquet-rs service |
| duckdb | 1.5.6 | Parquet SQL readback | MIT | https://pypi.org/pypi/duckdb/1.5.6/json | Runtime | embedded analytical queries | SQLite aggregate |
| structlog | 26.1.0 | structured technical logging | MIT OR Apache-2.0 | https://pypi.org/pypi/structlog/26.1.0/json | Runtime | structured events | logging JSON formatter |
| pyside6 | 6.11.2 | Qt Quick QML shell | LGPL-3.0-only | https://pypi.org/pypi/pyside6/6.11.2/json | Runtime | QML bridge | other GUI stack |
| pyserial | 3.5 | read-only COM candidate listing | BSD-3-Clause | https://pypi.org/pypi/pyserial/3.5/json | Runtime | cross-platform enumeration | OS API |
| jsonschema | 4.26.0 | plugin manifest schema | MIT | https://pypi.org/pypi/jsonschema/4.26.0/json | Runtime | language-neutral contract | Pydantic only |
| tzdata | 2026.4 | Windows UTC Parquet replay | Apache-2.0 | https://pypi.org/pypi/tzdata/2026.4/json | Runtime on Windows | timezone conversion | system zoneinfo |
| pyusb | 1.3.1 | optional USB candidate listing | BSD-3-Clause | https://pypi.org/pypi/pyusb/1.3.1/json | Device-extra | transport candidate | OS API |
| hidapi | 0.15.0 | optional HID transport | BSD-3-Clause | https://pypi.org/pypi/hidapi/0.15.0/json | Device-extra | future HID access | OS API |
| bleak | 1.1.1 | optional BLE transport | MIT | https://pypi.org/pypi/bleak/1.1.1/json | Device-extra | future BLE access | OS API |
| pytest | 9.1.1 | automated tests | MIT | https://pypi.org/pypi/pytest/9.1.1/json | Dev | test runner | unittest |
| pytest-qt | 4.5.0 | Qt event-loop tests | MIT | https://pypi.org/pypi/pytest-qt/4.5.0/json | Dev | heartbeat checks | direct QCoreApplication |
| hypothesis | 6.168.3 | property tests | MPL-2.0 | https://pypi.org/pypi/hypothesis/6.168.3/json | Dev | invalid-input exploration | custom fuzzing |
| ruff | 0.16.9 | static lint | MIT | https://pypi.org/pypi/ruff/0.16.9/json | Dev | fast lint | flake8 |
| mypy | 1.20.2 | type analysis | MIT | https://pypi.org/pypi/mypy/1.20.2/json | Dev | type drift | pyright |

The license conclusion for optional `hidapi` selects its bundled BSD-style option; the wheel also declares GPL-3.0 as an alternative. Qt/PySide6 declares LGPL/GPL alternatives; this baseline uses only the audited Qt Quick module set under LGPL, with distribution obligations still requiring packaging review.

`hatchling` is a PEP 517 build backend resolved in build isolation, not a locked application dependency. `uv` is a bootstrap/development tool, not in this project lock. The local project package has no distribution license selected and is `NOASSERTION` in SPDX; this is separate from third-party license review.

License evidence: `docs/lock_license_evidence.json` records version-pinned PyPI metadata URLs and reviewed conclusions. No locked third-party package is `UNKNOWN`.
