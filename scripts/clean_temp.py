"""清理 pytest 运行时残留目录和 __pycache__。

用法:
    python scripts/clean_temp.py          # 清理并报告
    python scripts/clean_temp.py -q       # 静默模式
"""

import argparse
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = [
    '.pytest_runtime_*',
    '.pytest_basetemp_*',
    '.pytest_cache',
]


def _on_rm_error(func, fpath, exc_info):
    try:
        os.chmod(fpath, stat.S_IWRITE)
        func(fpath)
    except Exception:
        pass


def clean_dir(path, quiet=False):
    if not path.exists():
        return 0
    try:
        shutil.rmtree(path, onerror=_on_rm_error)
        if not quiet:
            print(f'  已删除: {path.name}')
        return 1
    except Exception as exc:
        if not quiet:
            print(f'  跳过:   {path.name} ({exc})')
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='清理 pytest 残留临时目录')
    parser.add_argument('-q', '--quiet', action='store_true', help='静默模式')
    args = parser.parse_args(argv)

    removed = 0
    skipped = 0

    if not args.quiet:
        print(f'清理目录: {ROOT}')

    for pattern in PATTERNS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_dir():
                result = clean_dir(path, quiet=args.quiet)
                if result:
                    removed += 1
                else:
                    skipped += 1

    pycache_count = 0
    for path in sorted(ROOT.rglob('__pycache__')):
        if '.venv' in path.parts or 'build' in path.parts or 'dist' in path.parts:
            continue
        result = clean_dir(path, quiet=args.quiet)
        if result:
            removed += 1
            pycache_count += 1
        else:
            skipped += 1

    if not args.quiet:
        print(f'\n已清理: {removed} 个目录（含 {pycache_count} 个 __pycache__）')
        if skipped:
            print(f'已跳过: {skipped} 个目录')

    return 0 if skipped == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
