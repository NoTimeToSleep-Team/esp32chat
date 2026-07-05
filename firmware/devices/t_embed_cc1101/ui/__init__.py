"""T-Embed CC1101 text-first client UI modules."""

from .command_map import T_EMBED_CC1101_CLIENT_COMMANDS, command_path_set
from .controller import TEmbedCC1101ClientController
from .models import BufferEntry, BufferFlushResult, BufferSnapshot, SendOutcome, TemplateCatalog, TemplateEntry

__all__ = [
    "BufferEntry",
    "BufferFlushResult",
    "BufferSnapshot",
    "SendOutcome",
    "T_EMBED_CC1101_CLIENT_COMMANDS",
    "TEmbedCC1101ClientController",
    "TemplateCatalog",
    "TemplateEntry",
    "command_path_set",
]
