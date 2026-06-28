"""统一管理应用资源目录与可写运行时目录。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    """应用使用的全部路径。

    resource_dir 只读，保存打包资源；其余路径位于 base_dir，可持久化写入。
    """

    base_dir: Path
    resource_dir: Path

    @classmethod
    def create(cls, base_dir, resource_dir=None):
        base = Path(base_dir).resolve()
        resource = Path(resource_dir or base).resolve()
        return cls(base_dir=base, resource_dir=resource)

    @property
    def config_file(self) -> Path:
        return self.base_dir / 'config.json'

    @property
    def templates_dir(self) -> Path:
        return self.base_dir / 'templates'

    @property
    def uploads_dir(self) -> Path:
        return self.base_dir / 'uploads'

    @property
    def output_dir(self) -> Path:
        return self.base_dir / 'output'

    @property
    def sessions_dir(self) -> Path:
        return self.base_dir / 'sessions'

    @property
    def data_dir(self) -> Path:
        return self.base_dir / 'data'

    @property
    def database_file(self) -> Path:
        return self.data_dir / 'contracts.db'

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / 'backups'

    @property
    def excel_bill_defaults_dir(self) -> Path:
        return self.data_dir / 'excel_bill_defaults'

    @property
    def procurement_dir(self) -> Path:
        return self.output_dir / 'procurement'

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / 'logs'

    def ensure_writable_dirs(self) -> None:
        for path in (
            self.templates_dir,
            self.uploads_dir,
            self.output_dir,
            self.sessions_dir,
            self.data_dir,
            self.backups_dir,
            self.excel_bill_defaults_dir,
            self.procurement_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
