import json
from pathlib import Path

import pytest

from scripts.generate_sbom import (
    build_sbom,
    read_npm_lock,
    read_pinned_requirements,
)


def test_build_sbom_contains_application_and_locked_dependencies(tmp_path):
    requirements = tmp_path / 'requirements.lock'
    requirements.write_text(
        'Flask==3.1.3\npywin32==311; sys_platform == "win32"\n',
        encoding='utf-8',
    )
    version = tmp_path / 'version.txt'
    version.write_text('1.2.3\n', encoding='utf-8')

    sbom = build_sbom(requirements, version)

    assert sbom['bomFormat'] == 'CycloneDX'
    assert sbom['metadata']['component']['version'] == '1.2.3'
    assert sbom['metadata']['component']['copyright'] == 'Copyright (c) 2026 Shao'
    assert [item['name'] for item in sbom['components']] == ['Flask', 'pywin32']
    assert sbom['components'][1]['properties'][0]['value'] == 'sys_platform == "win32"'
    json.dumps(sbom)


def test_sbom_rejects_unpinned_dependency(tmp_path):
    requirements = tmp_path / 'requirements.lock'
    requirements.write_text('Flask>=3\n', encoding='utf-8')

    with pytest.raises(ValueError, match='依赖未锁定'):
        read_pinned_requirements(requirements)


def test_sbom_parses_pip_compile_hash_continuations(tmp_path):
    requirements = tmp_path / 'requirements.lock'
    requirements.write_text(
        'Flask==3.1.3 \\\n'
        '    --hash=sha256:abc \\\n'
        '    --hash=sha256:def\n'
        'pywin32==311 ; sys_platform == "win32" \\\n'
        '    --hash=sha256:123\n',
        encoding='utf-8',
    )

    components = read_pinned_requirements(requirements)

    assert [(item['name'], item['version']) for item in components] == [
        ('Flask', '3.1.3'),
        ('pywin32', '311'),
    ]
    assert components[1]['properties'][0]['value'] == 'sys_platform == "win32"'


def test_repository_sbom_uses_remediated_runtime_lock():
    root = Path(__file__).resolve().parents[1]
    sbom = build_sbom(root / 'requirements.lock', root / 'version.txt')
    versions = {item['name'].lower(): item['version'] for item in sbom['components']}

    assert versions['cryptography'] == '50.0.0'


def test_sbom_includes_npm_build_chain_and_vendored_assets(tmp_path):
    requirements = tmp_path / 'requirements.lock'
    requirements.write_text('Flask==3.1.3\n', encoding='utf-8')
    version = tmp_path / 'version.txt'
    version.write_text('1.2.3\n', encoding='utf-8')
    package_lock = tmp_path / 'package-lock.json'
    package_lock.write_text(
        json.dumps({
            'packages': {
                '': {'name': 'root'},
                'node_modules/postcss': {'version': '8.5.26', 'dev': True},
                'node_modules/chokidar/node_modules/glob-parent': {
                    'version': '5.1.2',
                    'dev': True,
                },
                'node_modules/tool/node_modules/@scope/helper': {
                    'version': '2.0.0',
                    'dev': True,
                },
            },
        }),
        encoding='utf-8',
    )
    vendored = tmp_path / 'static' / 'vendor' / 'alpine.min.js'
    vendored.parent.mkdir(parents=True)
    vendored.write_text('window.Alpine = {};', encoding='utf-8')

    npm_components = read_npm_lock(package_lock)
    assert {item['purl'] for item in npm_components} == {
        'pkg:npm/%40scope/helper@2.0.0',
        'pkg:npm/glob-parent@5.1.2',
        'pkg:npm/postcss@8.5.26',
    }
    assert {item['name'] for item in npm_components} == {
        '@scope/helper',
        'glob-parent',
        'postcss',
    }

    sbom = build_sbom(
        requirements,
        version,
        package_lock_path=package_lock,
        vendored_paths=(vendored,),
    )
    names = {component['name'] for component in sbom['components']}
    assert {'Flask', 'postcss', 'static/vendor/alpine.min.js'} <= names
