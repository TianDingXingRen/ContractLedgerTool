# Documentation Index

This project keeps the root README as the quick-start entrypoint. Longer design
and planning notes stay in this index so they do not compete with setup steps.

## Canonical Documents

- `README.md` - quick start, runtime configuration, and project map.
- `软件规格说明书.md` - product scope and functional specification.
- `合同生成工具_开发方案与测试方案.md` - legacy contract-generation plan and tests.
- `采购前置工作台与合同生成工具一体化_开发与测试方案.md` - procurement workflow plan and tests.
- `UI交互修复方案.md` - UI repair notes and follow-up design debt.
- `installer_assets/README_安装说明.txt` - installer usage notes.
- `installer_assets/README_EXE_使用说明.txt` - packaged EXE usage notes.

## Operational Notes

- Use `requirements.txt` for human-maintained dependency ranges.
- Use `requirements.lock` for reproducible installs.
- See `docs/technical-debt-audit.md` for the current repository audit and deferred non-security debt.
- Use `python scripts/demo_data.py sample-contracts` for bulk sample contracts.
- Use `python scripts/demo_data.py demo-flow` for end-to-end demo contracts.

## Cleanup Rule

Temporary notes should either be promoted into one of the canonical documents
above or moved under `docs/archive/` with a short reason. Template scratch files
such as `templates/_*.txt` should not be treated as project documentation.
