"""Static WO01 gates. Runs on Python 3.12 without installed runtime packages."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "batteryscope"
REQUIRED_DOCS = (
    "README.md", "docs/ARCHITECTURE.md", "docs/HARDWARE_STATUS.md", "docs/OSS_BOM.md",
    "docs/protocols/c2-pro.md", "docs/protocols/ebd-a20h.md", "schemas/plugin-manifest.schema.json",
    "docs/qt-modules.json", "docs/lock_license_evidence.json", "SBOM.spdx.json",
)
REQUIRED_ADRS = tuple(f"docs/adr/ADR-{number:03d}-" for number in range(1, 6))
PHYSICAL_METHODS = {
    "c2/driver.py": ("connect", "request_pdo", "request_pps", "firmware_command"),
    "ebd/driver.py": ("connect", "send_load_command", "set_constant_current", "set_constant_power",
                      "set_current", "set_power", "load_on", "load_off", "emergency_stop"),
}


def name_of(requirement: str) -> str:
    return re.split(r"[<>=!~;\[]", requirement, 1)[0].strip().lower().replace("_", "-")


def main(static_only: bool = False) -> int:
    violations: list[str] = []
    for relative in REQUIRED_DOCS:
        if not (ROOT / relative).is_file():
            violations.append(f"missing required file: {relative}")
    for prefix in REQUIRED_ADRS:
        if not list(ROOT.glob(prefix + "*.md")):
            violations.append(f"missing ADR: {prefix}")
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC).as_posix()
        tree = ast.parse(source, filename=relative)
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        if "QtGraphs" in source or "QtCharts" in source:
            violations.append(f"{relative}: prohibited Qt graph module")
        if relative.startswith("ui/") and any(module.startswith(("sqlite3", "duckdb", "serial", "usb", "pyarrow")) for module in imports):
            violations.append(f"{relative}: blocking backend import in UI")
        if relative.startswith("devices/") and any(module.startswith(("sqlite3", "batteryscope.storage", "batteryscope.app")) for module in imports):
            violations.append(f"{relative}: device depends on persistence/application")
        if relative.startswith("core/") and any(module.startswith(("batteryscope.devices", "batteryscope.storage", "PySide6")) for module in imports):
            violations.append(f"{relative}: core dependency direction")
    qml = (SRC / "ui" / "qml" / "Main.qml").read_text(encoding="utf-8")
    if "QtGraphs" in qml or "QtCharts" in qml:
        violations.append("QML imports prohibited Qt module")
    for relative, methods in PHYSICAL_METHODS.items():
        tree = ast.parse((SRC / "devices" / relative).read_text(encoding="utf-8"))
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        for method in methods:
            body = functions.get(method)
            if body is None or not any(isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                                       and isinstance(node.exc.func, ast.Name)
                                       and node.exc.func.id == "NotVerifiedProtocolError" for node in body.body):
                violations.append(f"{relative}.{method}: physical write guard missing")
    schema_path = ROOT / "schemas" / "plugin-manifest.schema.json"
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if not {"plugin_id", "capabilities", "supported_devices"}.issubset(schema.get("required", [])):
            violations.append("plugin manifest schema lacks required fields")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if pyproject["project"]["requires-python"] != ">=3.12,<3.13":
        violations.append("Python minor support exceeds validated 3.12")
    requirements = {name_of(item) for item in pyproject["project"]["dependencies"]}
    for group in pyproject.get("dependency-groups", {}).values():
        requirements.update(name_of(item) for item in group)
    bom = (ROOT / "docs" / "OSS_BOM.md").read_text(encoding="utf-8") if (ROOT / "docs" / "OSS_BOM.md").exists() else ""
    for name in sorted(requirements):
        if not re.search(r"^\| " + re.escape(name) + r" \|", bom, flags=re.MULTILINE | re.IGNORECASE):
            violations.append(f"OSS BOM missing declared dependency: {name}")
    if "| UNKNOWN |" in bom:
        violations.append("OSS BOM contains UNKNOWN license: manual review required")
    lock_path = ROOT / "uv.lock"
    if not lock_path.is_file() and not static_only:
        violations.append("uv.lock absent: reproducibility gate failed")
    elif lock_path.is_file():
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        locked = {name_of(package["name"]): package["version"] for package in lock.get("package", [])}
        for name in requirements:
            if name not in locked:
                violations.append(f"lock missing package: {name}")
            elif not re.search(r"^\| " + re.escape(name) + r" \| " + re.escape(locked[name]) + r" ",
                               bom, flags=re.MULTILINE | re.IGNORECASE):
                violations.append(f"BOM version does not match lock: {name}")
        sbom_path = ROOT / "SBOM.spdx.json"
        evidence_path = ROOT / "docs" / "lock_license_evidence.json"
        if sbom_path.exists() and evidence_path.exists():
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            spdx = {name_of(package["name"]): package["versionInfo"] for package in sbom.get("packages", [])}
            reviewed = {name_of(name): item["version"] for name, item in evidence.items()}
            if locked != spdx or locked != reviewed:
                violations.append("SBOM/license evidence package names or versions differ from uv.lock")
            for package in sbom.get("packages", []):
                name = name_of(package["name"])
                if name != "batteryscope-studio" and package.get("licenseConcluded") in (None, "UNKNOWN", "NOASSERTION"):
                    violations.append(f"manual license review required: {name}")
                if name in evidence and package.get("licenseConcluded") != evidence[name]["license_concluded"]:
                    violations.append(f"SBOM license differs from reviewed evidence: {name}")
    result = subprocess.run(["git", "check-ignore", "--quiet", "runtime/fixture.raw"], cwd=ROOT, check=False)
    if result.returncode != 0:
        violations.append("runtime/ is not ignored by Git")
    if violations:
        print("\n".join(violations))
        return 1
    print("architecture boundary PASS")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true", help="skip the lockfile availability gate")
    sys.exit(main(parser.parse_args().static_only))
