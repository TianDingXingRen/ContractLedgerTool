# SPDX-FileCopyrightText: 2026 Shao
# SPDX-License-Identifier: MIT
"""Generate a CycloneDX SBOM for the packaged Python runtime dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


PIN_PATTERN = re.compile(r'^([A-Za-z0-9_.-]+)==([^;\s]+)\s*(?:;\s*(.+))?$')


def read_pinned_requirements(path: Path) -> list[dict[str, str]]:
    components = []
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith('-'):
            continue
        if line.endswith('\\'):
            line = line[:-1].rstrip()
        match = PIN_PATTERN.match(line)
        if not match:
            raise ValueError(f'依赖未锁定为 name==version: {line}')
        name, version, marker = match.groups()
        normalized = name.lower().replace('_', '-')
        purl = f'pkg:pypi/{normalized}@{version}'
        component = {
            'type': 'library',
            'bom-ref': purl,
            'name': name,
            'version': version,
            'purl': purl,
            'scope': 'required',
        }
        if marker:
            component['properties'] = [{'name': 'python:environment-marker', 'value': marker}]
        components.append(component)
    return sorted(components, key=lambda item: item['purl'])


def read_npm_lock(path: Path) -> list[dict[str, str]]:
    """Return every locked npm package, including build-only transitive tools."""
    payload = json.loads(path.read_text(encoding='utf-8'))
    components_by_ref = {}
    for location, metadata in payload.get('packages', {}).items():
        if not location.startswith('node_modules/') or not metadata.get('version'):
            continue
        # package-lock v2/v3 records nested installations as e.g.
        # ``node_modules/chokidar/node_modules/glob-parent``.  The component
        # name is the package after the final node_modules segment; retaining
        # the installation path would create an invalid npm package name/PURL.
        name = location.rsplit('node_modules/', 1)[-1]
        version = str(metadata['version'])
        purl = f'pkg:npm/{quote(name, safe="/")}@{version}'
        component = {
            'type': 'library',
            'bom-ref': purl,
            'name': name,
            'version': version,
            'purl': purl,
            'scope': 'optional' if metadata.get('dev') else 'required',
        }
        components_by_ref[purl] = component
    return sorted(components_by_ref.values(), key=lambda item: item['purl'])


def vendored_file_component(path: Path, *, root: Path) -> dict[str, object]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return {
        'type': 'file',
        'bom-ref': f'urn:sha256:{digest}',
        'name': relative,
        'scope': 'required',
        'hashes': [{'alg': 'SHA-256', 'content': digest}],
        'properties': [{'name': 'distribution', 'value': 'vendored'}],
    }


def build_sbom(
    requirements_path: Path,
    version_path: Path,
    *,
    package_lock_path: Path | None = None,
    vendored_paths: tuple[Path, ...] = (),
) -> dict:
    version = version_path.read_text(encoding='utf-8').strip()
    if not version:
        raise ValueError('version.txt 不能为空')
    components = read_pinned_requirements(requirements_path)
    if package_lock_path is not None:
        components.extend(read_npm_lock(package_lock_path))
    repository_root = version_path.resolve().parent
    components.extend(
        vendored_file_component(path, root=repository_root)
        for path in vendored_paths
    )
    components.sort(key=lambda item: item['bom-ref'])
    root_ref = f'pkg:github/TianDingXingRen/ContractLedgerTool@{version}'
    serial_seed = '\n'.join(
        [root_ref, *(str(item['bom-ref']) for item in components)]
    )
    return {
        'bomFormat': 'CycloneDX',
        'specVersion': '1.5',
        'serialNumber': f'urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)}',
        'version': 1,
        'metadata': {
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'component': {
                'type': 'application',
                'bom-ref': root_ref,
                'name': 'ContractLedgerTool',
                'version': version,
                'purl': root_ref,
                'copyright': 'Copyright (c) 2026 Shao',
                'licenses': [{'license': {'id': 'MIT'}}],
            },
        },
        'components': components,
        'dependencies': [{
            'ref': root_ref,
            'dependsOn': [item['bom-ref'] for item in components],
        }],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requirements', default='requirements.lock')
    parser.add_argument('--version-file', default='version.txt')
    parser.add_argument('--package-lock', default='package-lock.json')
    parser.add_argument(
        '--vendored', action='append', default=['static/vendor/alpine.min.js']
    )
    parser.add_argument('--output', default='dist/release/ContractLedgerTool.sbom.cdx.json')
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    package_lock = Path(args.package_lock)
    vendored_paths = tuple(
        path for value in args.vendored if (path := Path(value)).is_file()
    )
    payload = build_sbom(
        Path(args.requirements),
        Path(args.version_file),
        package_lock_path=package_lock if package_lock.is_file() else None,
        vendored_paths=vendored_paths,
    )
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(f'Wrote {len(payload["components"])} components to {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
