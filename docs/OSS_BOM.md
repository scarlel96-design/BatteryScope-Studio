# OSS bill of materials (declared direct dependencies)

This table describes declared dependencies, not an installed or locked environment. `uv.lock` resolution and package-license audit must be performed on an environment with package access before release. Exact versions are intentionally recorded as `UNRESOLVED` until a lock is generated; architecture verification reports this as a failed reproducibility gate.

| Name | Version | Purpose | License | Repository | Scope | Reason selected | Alternative |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pydantic | UNRESOLVED (`>=2.10,<3`) | typed validation | MIT | https://github.com/pydantic/pydantic | Runtime | strict models | attrs |
| pyarrow | UNRESOLVED (`>=19,<25`) | Arrow/Parquet | Apache-2.0 | https://github.com/apache/arrow | Runtime | columnar raw | parquet-rs service |
| duckdb | UNRESOLVED (`>=1.2,<2`) | raw SQL readback | MIT | https://github.com/duckdb/duckdb | Runtime | embedded analytics | SQLite aggregate |
| structlog | UNRESOLVED (`>=25,<27`) | structured logging | MIT/Apache-2.0 | https://github.com/hynek/structlog | Runtime | structured events | logging JSON formatter |
| PySide6 | UNRESOLVED (`>=6.8,<7`) | Qt Quick shell | LGPL-3.0/commercial; module audit required | https://code.qt.io/cgit/pyside/pyside-setup.git | Runtime | QML bridge | other GUI stack |
| pyserial | UNRESOLVED (`>=3.5,<4`) | serial candidate listing | BSD-3-Clause | https://github.com/pyserial/pyserial | Runtime | cross-platform COM enumeration | OS API |
| jsonschema | UNRESOLVED (`>=4.23,<5`) | manifest schema validation | MIT | https://github.com/python-jsonschema/jsonschema | Runtime | language-neutral plugin contract | Pydantic only |
| pyusb | UNRESOLVED (`>=1.3,<2`) | generic USB enumeration | BSD-3-Clause | https://github.com/pyusb/pyusb | Device-extra | transport candidate | OS API |
| hidapi | UNRESOLVED (`>=0.14,<1`) | future HID transport | BSD/MIT/GPL selectable; review binary build | https://github.com/trezor/cython-hidapi | Device-extra | optional HID access | OS API |
| bleak | UNRESOLVED (`>=0.22,<2`) | future BLE transport | MIT | https://github.com/hbldh/bleak | Device-extra | cross-platform BLE | OS API |
| pytest | UNRESOLVED (`>=8.3,<10`) | tests | MIT | https://github.com/pytest-dev/pytest | Dev | test runner | unittest |
| pytest-qt | UNRESOLVED (`>=4.4,<5`) | Qt tests | MIT | https://github.com/pytest-dev/pytest-qt | Dev | event-loop checks | direct QCoreApplication |
| hypothesis | UNRESOLVED (`>=6.120,<7`) | property tests | MPL-2.0 | https://github.com/HypothesisWorks/hypothesis | Dev | invalid-input exploration | custom fuzzing |
| ruff | UNRESOLVED (`>=0.9,<1`) | static lint | MIT | https://github.com/astral-sh/ruff | Dev | fast lint | flake8 |
| mypy | UNRESOLVED (`>=1.14,<2`) | type checks | MIT | https://github.com/python/mypy | Dev | type drift | pyright |
| hatchling | UNRESOLVED (`>=1.26`) | package build | MIT | https://github.com/pypa/hatch | Build | PEP 517 backend | setuptools |

Python `sqlite3` and `json` are standard library modules. `uv` is a development tool and is absent from the current host; its lock and resolved version are pending. Transitive dependency names, versions, and licenses must come from the eventual lock/SBOM, not this direct-dependency table.
