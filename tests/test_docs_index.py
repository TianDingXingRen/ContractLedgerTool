from pathlib import Path


def test_docs_index_names_canonical_documents():
    root = Path(__file__).resolve().parents[1]
    index = (root / 'docs' / 'README.md').read_text(encoding='utf-8')

    for filename in [
        'README.md',
        '软件规格说明书.md',
        '合同生成工具_开发方案与测试方案.md',
        '采购前置工作台与合同生成工具一体化_开发与测试方案.md',
        'UI交互修复方案.md',
        'requirements.lock',
        'scripts/demo_data.py',
    ]:
        assert filename in index
