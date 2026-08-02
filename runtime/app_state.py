"""应用全局单例状态管理。

替代各模块（ledger_store、template_def、helpers、autostart）中分散的模块级变量。
所有路径状态通过 RuntimePaths 统一管理，避免测试和多实例场景下的互相污染。
"""

from __future__ import annotations

from typing import Optional

from runtime.paths import RuntimePaths


class _AppStateHandle:
    """轻量级应用状态句柄，提供路径延迟求值。

    各模块通过此对象访问运行时路径，而非模块级变量。
    """

    __slots__ = ('_context',)

    def __init__(self):
        self._context: Optional[RuntimePaths] = None

    @property
    def paths(self) -> RuntimePaths:
        if self._context is None:
            raise RuntimeError(
                '应用路径未初始化，请先调用 app_state.configure() '
                '或在 create_app() 中完成初始化'
            )
        return self._context

    def configure(self, paths: RuntimePaths):
        self._context = paths

    def is_configured(self) -> bool:
        return self._context is not None

    @property
    def base_dir(self) -> str:
        return str(self.paths.base_dir)

    @property
    def resource_dir(self) -> str:
        return str(self.paths.resource_dir)

    @property
    def uploads_dir(self) -> str:
        return str(self.paths.uploads_dir)

    @property
    def output_dir(self) -> str:
        return str(self.paths.output_dir)

    @property
    def sessions_dir(self) -> str:
        return str(self.paths.sessions_dir)

    @property
    def data_dir(self) -> str:
        return str(self.paths.data_dir)

    @property
    def database_file(self) -> str:
        return str(self.paths.database_file)

    @property
    def backups_dir(self) -> str:
        return str(self.paths.backups_dir)

    @property
    def templates_dir(self) -> str:
        return str(self.paths.templates_dir)

    @property
    def logs_dir(self) -> str:
        return str(self.paths.logs_dir)

    @property
    def procurement_dir(self) -> str:
        return str(self.paths.procurement_dir)

    @property
    def excel_bill_defaults_dir(self) -> str:
        return str(self.paths.excel_bill_defaults_dir)


app_state = _AppStateHandle()
