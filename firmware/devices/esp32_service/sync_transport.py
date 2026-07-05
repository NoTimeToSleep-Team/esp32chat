from __future__ import annotations

from collections.abc import Callable

from firmware.common.protocol.models import Envelope
from firmware.common.transport import InMemoryTransportAdapter, TransportAdapter, UartFramedTransportAdapter

from .config import Esp32ServiceConfig

EnvelopeHandler = Callable[[Envelope], Envelope]
UartExchange = Callable[[bytes], bytes]

SYNC_TRANSPORT_INMEMORY = "inmemory"
SYNC_TRANSPORT_UART = "uart"


def build_sync_transport_adapter(
    config: Esp32ServiceConfig,
    *,
    envelope_handler: EnvelopeHandler | None = None,
    uart_exchange: UartExchange | None = None,
) -> TransportAdapter:
    transport = config.sync_transport.strip().lower()
    if transport == SYNC_TRANSPORT_INMEMORY:
        return InMemoryTransportAdapter(handler=envelope_handler)

    if transport == SYNC_TRANSPORT_UART:
        if uart_exchange is None:
            raise RuntimeError("uart_exchange callback is required when sync_transport='uart'")
        return UartFramedTransportAdapter(
            exchange=uart_exchange,
            require_ack=config.sync_uart_ack_required,
        )

    raise RuntimeError(
        f"unsupported sync_transport: {config.sync_transport!r}; expected '{SYNC_TRANSPORT_INMEMORY}' or '{SYNC_TRANSPORT_UART}'"
    )
