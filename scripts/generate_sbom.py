# SPDX-FileCopyrightText: 2026 Shao
# SPDX-License-Identifier: MIT
"""Generate a CycloneDX SBOM for the packaged Python runtime dependencies."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


PIN_PATTERN = re.compile(r'^([A-Za-z0-9_.-]+)==([^;\s]+)(?:;\s*(.+))?$')


def read_pinned_requirements(path: Path) -> list[dict[str, str]]:
    components = []
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith('-'):
            continue
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


def build_sbom(requirements_path: Path, version_path: Path) -> dict:
    version = version_path.read_text(encoding='utf-8').strip()
    if not version:
        raise ValueError('version.txt 不能为空')
    components = read_pinned_requirements(requirements_path)
    root_ref = f'pkg:github/TianDingXingRen/ContractLedgerTool@{version}'
    serial_seed = '\n'.join([root_ref, *(item['purl'] for item in components)])
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
    parser.add_argument('--output', default='dist/release/ContractLedgerTool.sbom.cdx.json')
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_sbom(Path(args.requirements), Path(args.version_file))
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    print(f'Wrote {len(payload["components"])} components to {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
