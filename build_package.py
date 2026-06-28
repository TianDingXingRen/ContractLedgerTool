# -*- coding: utf-8 -*-
"""将合同管理工具打包为桌面安装包 zip。"""

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "build" / "_installer_stage"
APP = STAGE / "app"
DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"

# ── 排除的文件/目录 ──
SKIP_FILES = {
    ".gitignore", ".secret_key", "README.md",
    "demo_flow_data.py",
    "build_exe.py", "build_desktop_exe.py", "build_installer.py", "build_package.py", "build_icons.py",
    "启动合同生成工具.bat", "启动合同生成工具_autostart.bat",
}

SKIP_FILE_PREFIXES = ("test_",)

SKIP_TEMPLATE_FILES = {
    "test.contract-template",
    "Template1_Test.contract-template",
    "Template2_Test.contract-template",
    "backups.html",  # 运行时生成的备份页引用
}

SKIP_DIRS = {
    "__pycache__", ".git", "build", "dist", "logs", "output",
    "sessions", "data", "installer_assets", "scripts",
}


def reset_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_dir(src: Path, dst: Path):
    """递归复制目录，排除 __pycache__ 和 .pyc"""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in SKIP_DIRS:
            continue
        if item.name.endswith(".pyc") or item.name.endswith(".pyo"):
            continue
        if item.is_file():
            shutil.copy2(item, dst / item.name)
        elif item.is_dir():
            copy_dir(item, dst / item.name)


def main():
    print("打包合同管理工具安装包...")

    # ── 清理并创建 stage 目录 ──
    reset_dir(STAGE)
    reset_dir(APP)

    # ── 复制安装脚本到 stage 根目录 ──
    copy_file(ROOT / "install.ps1", STAGE / "install.ps1")
    copy_file(ROOT / "install.bat", STAGE / "install.bat")
    print("  install.ps1")
    print("  install.bat")

    # ── 复制 Python 源文件 ──
    for py_file in sorted(ROOT.glob("*.py")):
        if py_file.name in SKIP_FILES:
            continue
        if py_file.name.startswith(SKIP_FILE_PREFIXES):
            continue
        copy_file(py_file, APP / py_file.name)
        print(f"  {py_file.name}")

    # ── 复制子包目录（core/、runtime/） ──
    for pkg in ("core", "runtime"):
        src_pkg = ROOT / pkg
        if src_pkg.is_dir():
            copy_dir(src_pkg, APP / pkg)
            print(f"  {pkg}/")

    # ── 复制 requirements.txt ──
    copy_file(ROOT / "requirements.txt", APP / "requirements.txt")
    print("  requirements.txt")

    # ── 复制运行时脚本 ──
    for script in ["setup_autostart.ps1", "setup_autostart_remove.ps1"]:
        src = ROOT / script
        if src.exists():
            copy_file(src, APP / script)
            print(f"  {script}")

    # ── 从 installer_assets 复制运行时脚本 ──
    for script in ["start.ps1", "stop.ps1"]:
        src = ROOT / "installer_assets" / script
        if src.exists():
            copy_file(src, APP / script)
            print(f"  {script}")

    # ── 复制 routes/ ──
    copy_dir(ROOT / "routes", APP / "routes")
    print("  routes/")

    # ── 复制 utils/ ──
    copy_dir(ROOT / "utils", APP / "utils")
    print("  utils/")

    # ── 复制 static/ ──
    copy_dir(ROOT / "static", APP / "static")
    print("  static/")

    # ── 复制 templates/（HTML + 合同模板，排除测试/临时文件） ──
    tmpl_dst = APP / "templates"
    tmpl_dst.mkdir(parents=True, exist_ok=True)

    for html in sorted((ROOT / "templates").rglob("*.html")):
        rel_path = html.relative_to(ROOT / "templates")
        copy_file(html, tmpl_dst / rel_path)
        print(f"  templates/{rel_path}")

    for ct in sorted((ROOT / "templates").glob("*.contract-template")):
        if ct.name in SKIP_TEMPLATE_FILES:
            continue
        copy_file(ct, tmpl_dst / ct.name)
        print(f"  templates/{ct.name}")

    # ── 创建空的 uploads 目录 ──
    (APP / "uploads").mkdir(exist_ok=True)
    print("  uploads/ (空)")

    # ── 打包为 zip ──
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"合同管理工具_安装包_{stamp}.zip"
    zip_path = DESKTOP / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(STAGE.rglob("*")):
            if fpath.is_file():
                zf.write(fpath, str(fpath.relative_to(STAGE)))

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    file_count = len(zf.namelist())

    print(f"\n  安装包已生成:")
    print(f"  {zip_path}")
    print(f"  大小: {size_mb:.1f} MB  |  文件数: {file_count}")

    # ── 清理 stage ──
    shutil.rmtree(STAGE, ignore_errors=True)


if __name__ == "__main__":
    main()
