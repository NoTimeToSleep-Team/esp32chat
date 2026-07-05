"""M5Cardputer external client profile-alignment modules."""

from .command_map import M5CARDPUTER_HANDHELD_COMMANDS, command_path_set
from .config import M5CardputerClientConfig
from .models import ClientConnectionState, HandheldVariant
from .profile_variants import load_handheld_variants
from .ui import HandheldSession, M5CardputerHandheldClientController

__all__ = [
    "ClientConnectionState",
    "HandheldVariant",
    "HandheldSession",
    "M5CARDPUTER_HANDHELD_COMMANDS",
    "M5CardputerClientConfig",
    "M5CardputerHandheldClientController",
    "command_path_set",
    "load_handheld_variants",
]
