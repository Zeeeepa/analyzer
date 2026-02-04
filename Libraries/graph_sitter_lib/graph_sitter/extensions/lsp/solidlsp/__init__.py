# ruff: noqa
# Lazy import to avoid dependency issues
def SolidLanguageServer():
    from .ls import SolidLanguageServer as _SolidLanguageServer
    return _SolidLanguageServer()
