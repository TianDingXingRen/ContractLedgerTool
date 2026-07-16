"""Runtime-scoped service and repository container."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any

from runtime.paths import RuntimePaths


class ModuleRepository:
    """Compatibility repository that delegates to an existing store facade."""

    def __init__(self, module: ModuleType):
        self._module = module

    def __getattr__(self, name):
        return getattr(self._module, name)


@dataclass(frozen=True)
class RuntimeServices:
    paths: RuntimePaths
    ledger: ModuleRepository
    procurement: ModuleRepository
    contract_generation: Any
    generation_recovery: Any


def create_runtime_services(paths: RuntimePaths) -> RuntimeServices:
    import ledger_store
    import procurement_store
    from services.contract_generation_service import ContractGenerationService
    from services.generation_recovery_service import GenerationRecoveryService

    ledger = ModuleRepository(ledger_store)
    procurement = ModuleRepository(procurement_store)
    return RuntimeServices(
        paths=paths,
        ledger=ledger,
        procurement=procurement,
        contract_generation=ContractGenerationService(
            ledger_store=ledger_store,
            procurement_store=procurement_store,
            staging_dir=paths.generation_staging_dir,
        ),
        generation_recovery=GenerationRecoveryService(
            ledger_store=ledger_store,
            output_dir=paths.output_dir,
            staging_dir=paths.generation_staging_dir,
            recovery_dir=paths.generation_recovery_dir,
        ),
    )
