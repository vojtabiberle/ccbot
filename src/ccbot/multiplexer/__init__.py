"""Multiplexer abstraction package — backend-agnostic terminal multiplexer API.

Re-exports the core types and provides a singleton factory:
  - MultiplexerBackend: ABC for all backends.
  - MuxWindow: Backend-agnostic window dataclass.
  - get_mux(): Returns the singleton backend instance (tmux or Zellij),
    selected by the MULTIPLEXER config value.
"""

from .base import MultiplexerBackend, MuxWindow

__all__ = ["MultiplexerBackend", "MuxWindow", "get_mux"]

_mux: MultiplexerBackend | None = None


def get_mux() -> MultiplexerBackend:
    """Return the singleton multiplexer backend.

    Lazily initialized on first call. Backend is selected by
    config.multiplexer_backend ("tmux" or "zellij").
    """
    global _mux
    if _mux is not None:
        return _mux

    from ..config import config

    if config.multiplexer_backend == "zellij":
        from .zellij_backend import ZellijBackend

        _mux = ZellijBackend(config.mux_session_name, config.mux_main_window_name)
    elif config.multiplexer_backend == "tmux":
        from .tmux_backend import TmuxBackend

        _mux = TmuxBackend(config.mux_session_name, config.mux_main_window_name)
    else:
        raise ValueError(
            f"Unknown multiplexer backend: {config.multiplexer_backend!r}. "
            f"Set MULTIPLEXER to 'tmux' or 'zellij'."
        )
    backend = _mux
    assert backend is not None
    return backend
