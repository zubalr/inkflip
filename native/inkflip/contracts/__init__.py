"""Inkflip contract validation and canonical identity (Python surface).

Importing this package is dependency-free: the validator module (which needs
the pinned ``jsonschema``) loads lazily on first attribute access. The single
authoritative schema is vendored byte-identically at
``schema/inkflip.schema.json`` by ``scripts/generate_contracts.py``.
"""

_LAZY = {
    'ContractError',
    'require',
    'loads_strict',
    'bounded',
    'canonical',
    'digest',
    'report_digest',
    'run_key',
    'seal',
    'occurrence_id',
    'normalize',
    'apply',
    'inverse',
    'unique',
    'validate',
    'validate_json',
    'validate_report',
    'WS',
    'SCHEMA',
    'SCHEMA_PATH',
    'VALIDATOR',
    'SCHEMA_VERSION',
    'CANONICALIZATION',
    'MAX_JSON_BYTES',
    'MAX_STRING_LENGTH',
    'MAX_DEPTH',
    'MAX_ASSET_BYTES',
    'MAX_ASSET_TOTAL',
    'MAX_PNG_PIXELS',
    'SAFE_INTEGER',
}

__all__ = sorted(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        from . import core

        return getattr(core, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__():
    return sorted(set(globals()) | _LAZY)
