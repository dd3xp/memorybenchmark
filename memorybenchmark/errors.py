"""Runner failures are distinct from agent task failures."""


class InfrastructureError(RuntimeError):
    pass


class AdapterError(ValueError):
    pass
