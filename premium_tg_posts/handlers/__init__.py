from .commands import router as commands_router
from .collector import router as collector_router
from .callbacks import router as callbacks_router

__all__ = ["callbacks_router", "collector_router", "commands_router"]
