"""Flipper Zero shell and limited-client MVP modules."""

from .command_map import FLIPPER_ZERO_COMMANDS, command_path_set
from .config import FlipperZeroConfig
from .controller import FlipperZeroController
from .models import CapabilitySnapshot, ConnectionState, FlipperScreen, FlipperSession, FlipperShellState
from .server_api import CommandSender, FlipperAuthGateway, GatewayError, UrllibCommandSender
from .shell import CapabilityDetector, FlipperZeroShell, StaticCapabilityDetector
from .ui import FLIPPER_ZERO_CLIENT_COMMANDS, FlipperZeroLimitedClientController
from .ui import command_path_set as client_command_path_set

__all__ = [
    "CapabilityDetector",
    "CapabilitySnapshot",
    "CommandSender",
    "ConnectionState",
    "FLIPPER_ZERO_CLIENT_COMMANDS",
    "FLIPPER_ZERO_COMMANDS",
    "FlipperAuthGateway",
    "FlipperZeroLimitedClientController",
    "FlipperScreen",
    "FlipperSession",
    "FlipperShellState",
    "FlipperZeroConfig",
    "FlipperZeroController",
    "FlipperZeroShell",
    "GatewayError",
    "StaticCapabilityDetector",
    "UrllibCommandSender",
    "client_command_path_set",
    "command_path_set",
]
