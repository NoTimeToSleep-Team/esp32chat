"""M5Cardputer built-in console shell/login + chat/blog/service MVP modules."""

from .blog import (
    BlogPostsScreenData,
    BlogPostView,
    ConsoleBlogGateway,
    M5CARDPUTER_CONSOLE_BLOG_COMMANDS,
    M5CardputerConsoleBlogController,
    blog_command_path_set,
)
from .chat import (
    ChatHistoryScreenData,
    ChatListScreenData,
    ChatMessageView,
    ChatRoomView,
    ChatSendResult,
    ConsoleChatGateway,
    M5CARDPUTER_CONSOLE_CHAT_COMMANDS,
    M5CardputerConsoleChatController,
    chat_command_path_set,
)
from .command_map import M5CARDPUTER_CONSOLE_COMMANDS, command_path_set
from .config import M5CardputerConsoleConfig
from .controller import M5CardputerConsoleController
from .models import ConnectionState, ConsoleSession, ConsoleShellState, NavigationScreen
from .service_actions import (
    ConsoleServiceActionsGateway,
    ConsoleServiceSnapshot,
    M5CARDPUTER_CONSOLE_SERVICE_COMMANDS,
    M5CardputerConsoleServiceController,
    service_command_path_set,
)
from .server_api import CommandSender, ConsoleAuthGateway, GatewayError, UrllibCommandSender
from .shell import M5CardputerConsoleShell

__all__ = [
    "BlogPostsScreenData",
    "BlogPostView",
    "CommandSender",
    "ChatHistoryScreenData",
    "ChatListScreenData",
    "ChatMessageView",
    "ChatRoomView",
    "ChatSendResult",
    "ConnectionState",
    "ConsoleAuthGateway",
    "ConsoleBlogGateway",
    "ConsoleChatGateway",
    "ConsoleSession",
    "ConsoleServiceActionsGateway",
    "ConsoleServiceSnapshot",
    "ConsoleShellState",
    "GatewayError",
    "M5CARDPUTER_CONSOLE_BLOG_COMMANDS",
    "M5CARDPUTER_CONSOLE_COMMANDS",
    "M5CARDPUTER_CONSOLE_CHAT_COMMANDS",
    "M5CARDPUTER_CONSOLE_SERVICE_COMMANDS",
    "M5CardputerConsoleConfig",
    "M5CardputerConsoleBlogController",
    "M5CardputerConsoleChatController",
    "M5CardputerConsoleController",
    "M5CardputerConsoleServiceController",
    "M5CardputerConsoleShell",
    "NavigationScreen",
    "UrllibCommandSender",
    "blog_command_path_set",
    "chat_command_path_set",
    "command_path_set",
    "service_command_path_set",
]
