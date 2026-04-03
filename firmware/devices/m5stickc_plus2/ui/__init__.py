"""M5StickC Plus2 compact client UI modules."""

from .command_map import M5STICKC_PLUS2_CLIENT_COMMANDS, command_path_set
from .controller import M5StickCPlus2ClientController

__all__ = [
    "M5STICKC_PLUS2_CLIENT_COMMANDS",
    "M5StickCPlus2ClientController",
    "command_path_set",
]
