"""Regenerate a deterministic direct BOM and SPDX package inventory from uv.lock."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "uv.lock"
EVIDENCE_PATH = ROOT / "docs" / "lock_license_evidence.json"

DETAILS = {
    "pydantic": ("typed configuration and sample validation", "Runtime", "strict models", "attrs"),
    "pyarrow": ("Arrow and ZSTD Parquet raw chunks", "Runtime", "columnar raw persistence", "parquet-rs service"),
    "duckdb": ("Parquet SQL readback", "Runtime", "embedded analytical queries", "SQLite aggregate"),
    "structlog": ("structured technical logging", "Runtime", "structured events", "logging JSON formatter"),
    "pyside6": ("Qt Quick QML shell", "Runtime", "QML bridge", "other GUI stack"),
    "pyserial": ("read-only COM candidate listing", "Runtime", "cross-platform enumeration", "OS API"),
    "jsonschema": ("plugin manifest schema", "Runtime", "language-neutral contract", "Pydantic only"),
    "tzdata": ("Windows UTC Parquet replay", "Runtime on Windows", "timezone conversion", "system zoneinfo"),
    "pyusb": ("optional USB candidate listing", "Device-extra", "transport candidate", "OS API"),
    "hidapi": ("optional HID transport", "Device-extra", "future HID access", "OS API"),
    "bleak": ("optional BLE transport", "Device-extra", "future BLE access", "OS API"),
    "pytest": ("automated tests", "Dev", "test runner", "unittest"),
    "pytest-qt": ("Qt event-loop tests", "Dev", "heartbeat checks", "direct QCoreApplication"),
    "hypothesis": ("property tests", "Dev", "invalid-input exploration", "custom fuzzing"),
    "ruff": ("static lint", "Dev", "fast lint", "flake8"),
    "mypy": ("type analysis", "Dev", "type drift", "pyright"),
}


def package_id(name: str) -> str:
    return "SPDXRef-Package-" + re.sub(r"[^A-Za-z0-9.-]", "-", name)


def main() -> None:
    lock_bytes = LOCK_PATH.read_bytes()
    lock = tomllib.loads(lock_bytes.decode("utf-8"))
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    packages = {item["name"]: item for item in lock["package"]}
    if set(packages) != set(evidence):
        raise ValueError("license evidence package set differs from uv.lock")
    for name, package in packages.items():
        item = evidence[name]
        if item["version"] != package["version"]:
            raise ValueError(f"license evidence version mismatch: {name}")
        if name != "batteryscope-studio" and item["license_concluded"] in {"UNKNOWN", "NOASSERTION"}:
            raise ValueError(f"manual license review required: {name}")

    bom = [
        "# OSS bill of materials (uv.lock)",
        "",
        (f"Resolver-locked graph: **{len(packages)} packages** across supported platform markers. "
         "Direct dependencies below are version-matched to `uv.lock`; optional device libraries "
         "are not part of the default runtime install. The full graph is in `SBOM.spdx.json`."),
        "",
        "| Name | Version | Purpose | License | Repository | Scope | Reason selected | Alternative |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, (purpose, scope, reason, alternative) in DETAILS.items():
        record = packages[name]
        license_id = evidence[name]["license_concluded"]
        repository = evidence[name]["metadata_url"]
        bom.append(f"| {name} | {record['version']} | {purpose} | {license_id} | {repository} | {scope} | {reason} | {alternative} |")
    bom += [
        "",
        ("The license conclusion for optional `hidapi` selects its bundled BSD-style option; "
         "the wheel also declares GPL-3.0 as an alternative. Qt/PySide6 declares LGPL/GPL "
         "alternatives; this baseline uses only the audited Qt Quick module set under LGPL, "
         "with distribution obligations still requiring packaging review."),
        "",
        ("`hatchling` is a PEP 517 build backend resolved in build isolation, not a locked "
         "application dependency. `uv` is a bootstrap/development tool, not in this project lock. "
         "The local project package has no distribution license selected and is `NOASSERTION` "
         "in SPDX; this is separate from third-party license review."),
        "",
        ("License evidence: `docs/lock_license_evidence.json` records version-pinned PyPI "
         "metadata URLs and reviewed conclusions. No locked third-party package is `UNKNOWN`."),
        "",
    ]
    (ROOT / "docs" / "OSS_BOM.md").write_text("\n".join(bom), encoding="utf-8")

    spdx_packages = []
    relationships = []
    for name in sorted(packages):
        package = packages[name]
        record = evidence[name]
        source = package.get("source", {})
        spdx_packages.append({
            "SPDXID": package_id(name),
            "name": name,
            "versionInfo": package["version"],
            "downloadLocation": record["metadata_url"] if "registry" in source else "NOASSERTION",
            "filesAnalyzed": False,
            "licenseDeclared": record["license_declared"],
            "licenseConcluded": record["license_concluded"],
            "copyrightText": "NOASSERTION",
            "externalRefs": ([{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl",
                               "referenceLocator": f"pkg:pypi/{name}@{package['version']}"}]
                             if "registry" in source else []),
        })
        for field in ("dependencies",):
            for dep in package.get(field, []):
                relationships.append({"spdxElementId": package_id(name),
                                      "relatedSpdxElement": package_id(dep["name"]),
                                      "relationshipType": "DEPENDS_ON"})
        for group in ("optional-dependencies", "dev-dependencies"):
            for dependencies in package.get(group, {}).values():
                for dep in dependencies:
                    relationships.append({"spdxElementId": package_id(name),
                                          "relatedSpdxElement": package_id(dep["name"]),
                                          "relationshipType": "DEPENDS_ON"})
    digest = hashlib.sha256(lock_bytes).hexdigest()
    sbom = {
        "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
        "name": "BatteryScope Studio WO01 locked dependency graph",
        "documentNamespace": f"https://github.com/scarlel96-design/BatteryScope-Studio/spdx/uv-lock-{digest}",
        "creationInfo": {"creators": ["Tool: tools/generate_supply_chain.py"], "created": "2026-10-02T00:00:00Z"},
        "documentDescribes": [package_id("batteryscope-studio")],
        "packages": spdx_packages,
        "relationships": sorted(relationships, key=lambda x: (x["spdxElementId"], x["relatedSpdxElement"])),
    }
    (ROOT / "SBOM.spdx.json").write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"supply chain generated: {len(spdx_packages)} locked packages, {len(DETAILS)} direct dependencies")


if __name__ == "__main__":
    main()
