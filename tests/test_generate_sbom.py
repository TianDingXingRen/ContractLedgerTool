import json

import pytest

from scripts.generate_sbom import build_sbom, read_pinned_requirements


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
