from __future__ import annotations

import time

from firmware.devices.m5cardputer_client.config import M5CardputerClientConfig
from firmware.devices.m5cardputer_client.ui.controller import M5CardputerHandheldClientController

from ..config import TEmbedCC1101Config
from ..server_api import CommandSender
from .models import BufferEntry, BufferFlushResult, BufferSnapshot, SendOutcome, TemplateCatalog, TemplateEntry

_DEFAULT_TEMPLATES: tuple[TemplateEntry, ...] = (
    TemplateEntry(
        template_id="ack",
        title="Acknowledge",
        body_text="Got it. Checking now.",
    ),
    TemplateEntry(
        template_id="eta5",
        title="ETA 5m",
        body_text="On my way. ETA 5 minutes.",
    ),
    TemplateEntry(
        template_id="busy",
        title="Busy",
        body_text="I am busy now. Will reply later.",
    ),
    TemplateEntry(
        template_id="online",
        title="Status online",
        body_text="Connection check: online.",
    ),
)


class TEmbedCC1101ClientController:
    def __init__(
        self,
        *,
        config: TEmbedCC1101Config,
        sender: CommandSender,
        templates: tuple[TemplateEntry, ...] | None = None,
    ) -> None:
        shared_config = M5CardputerClientConfig(
            profile_id=config.profile_id,
            base_url=config.base_url,
            request_timeout_s=config.request_timeout_s,
            client_kind=config.client_kind,
        )
        self._shared = M5CardputerHandheldClientController(config=shared_config, sender=sender)
        self._templates = templates or _DEFAULT_TEMPLATES
        self._buffer: list[BufferEntry] = []
        self._buffer_seq = 1

    @property
    def session(self):
        return self._shared.session

    def secure_login(self, *, login: str, password: str):
        return self._shared.secure_login(login=login, password=password)

    def logout(self) -> bool:
        return self._shared.logout()

    def list_chats(self):
        return self._shared.list_chats()

    def load_messages(self, *, chat_id: int, limit: int = 100, offset: int = 0):
        return self._shared.load_messages(chat_id=chat_id, limit=limit, offset=offset)

    def send_template(
        self,
        *,
        chat_id: int,
        template_id: str,
        client_message_id: str | None = None,
        now_ms: int | None = None,
    ) -> SendOutcome:
        template = self._template_by_id(template_id)
        return self.send_text(
            chat_id=chat_id,
            body_text=template.body_text,
            client_message_id=client_message_id,
            now_ms=now_ms,
        )

    def send_text(
        self,
        *,
        chat_id: int,
        body_text: str,
        client_message_id: str | None = None,
        now_ms: int | None = None,
    ) -> SendOutcome:
        if self.session is None:
            raise RuntimeError("operation requires authenticated t-embed session")

        resolved_client_message_id = client_message_id or self._next_generated_client_message_id()
        try:
            result = self._shared.send_text(
                chat_id=chat_id,
                body_text=body_text,
                client_message_id=resolved_client_message_id,
            )
        except RuntimeError as exc:
            entry = self._enqueue_buffer(
                chat_id=chat_id,
                body_text=body_text,
                client_message_id=resolved_client_message_id,
                now_ms=now_ms,
                error_message=str(exc),
            )
            return SendOutcome(
                status="buffered",
                client_message_id=entry.client_message_id,
                message_id=None,
                buffered_count=len(self._buffer),
            )

        result_client_message_id = result.message.client_message_id or resolved_client_message_id
        return SendOutcome(
            status="sent",
            client_message_id=result_client_message_id,
            message_id=result.message.message_id,
            buffered_count=len(self._buffer),
        )

    def list_posts(self, *, limit: int = 20, offset: int = 0):
        return self._shared.list_posts(limit=limit, offset=offset)

    def get_post(self, *, post_id: int):
        return self._shared.get_post(post_id=post_id)

    def list_templates(self) -> TemplateCatalog:
        return TemplateCatalog(count=len(self._templates), items=tuple(self._templates))

    def list_buffered(self) -> BufferSnapshot:
        return BufferSnapshot(count=len(self._buffer), items=tuple(self._buffer))

    def flush_buffer(self, *, limit: int = 10) -> BufferFlushResult:
        if limit < 1:
            raise RuntimeError("flush limit must be >= 1")
        if self.session is None:
            raise RuntimeError("flush_buffer requires authenticated t-embed session")

        attempted = 0
        sent = 0
        remaining: list[BufferEntry] = []

        for item in self._buffer:
            if attempted >= limit:
                remaining.append(item)
                continue

            attempted += 1
            try:
                self._shared.send_text(
                    chat_id=item.chat_id,
                    body_text=item.body_text,
                    client_message_id=item.client_message_id,
                )
                sent += 1
            except RuntimeError as exc:
                remaining.append(
                    BufferEntry(
                        buffer_key=item.buffer_key,
                        chat_id=item.chat_id,
                        body_text=item.body_text,
                        client_message_id=item.client_message_id,
                        queued_at_ms=item.queued_at_ms,
                        attempts=item.attempts + 1,
                        last_error=str(exc),
                    )
                )

        self._buffer = remaining
        return BufferFlushResult(attempted=attempted, sent=sent, remaining=len(self._buffer))

    def _template_by_id(self, template_id: str) -> TemplateEntry:
        for item in self._templates:
            if item.template_id == template_id:
                return item
        raise RuntimeError(f"unknown template_id: {template_id}")

    def _next_generated_client_message_id(self) -> str:
        value = f"t-embed-msg-{self._buffer_seq:06d}"
        self._buffer_seq += 1
        return value

    def _next_buffer_key(self) -> str:
        value = f"buffer-{self._buffer_seq:06d}"
        self._buffer_seq += 1
        return value

    def _enqueue_buffer(
        self,
        *,
        chat_id: int,
        body_text: str,
        client_message_id: str,
        now_ms: int | None,
        error_message: str,
    ) -> BufferEntry:
        queued_at = int(time.time() * 1000) if now_ms is None else now_ms

        for index, item in enumerate(self._buffer):
            if item.client_message_id != client_message_id:
                continue
            updated = BufferEntry(
                buffer_key=item.buffer_key,
                chat_id=chat_id,
                body_text=body_text,
                client_message_id=client_message_id,
                queued_at_ms=item.queued_at_ms,
                attempts=item.attempts + 1,
                last_error=error_message,
            )
            self._buffer[index] = updated
            return updated

        created = BufferEntry(
            buffer_key=self._next_buffer_key(),
            chat_id=chat_id,
            body_text=body_text,
            client_message_id=client_message_id,
            queued_at_ms=queued_at,
            attempts=1,
            last_error=error_message,
        )
        self._buffer.append(created)
        return created
