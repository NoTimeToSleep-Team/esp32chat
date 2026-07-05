from __future__ import annotations


class ProtocolError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProtocolVersionError(ProtocolError):
    def __init__(self, message: str) -> None:
        super().__init__("unsupported_protocol_version", message)


class UnsupportedMessageTypeError(ProtocolError):
    def __init__(self, message: str) -> None:
        super().__init__("unsupported_message_type", message)


class ProtocolValidationError(ProtocolError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_payload", message)
