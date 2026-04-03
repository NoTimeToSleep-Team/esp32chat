from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models import ClientKind, MessageDraft
from app.realtime import ChatRealtimeBroker, chat_message_event, chat_message_payload
from app.services.auth import AuthError, AuthService
from app.services.chat import ChatError, ChatService


router = APIRouter(tags=["realtime"])


def _auth_service(websocket: WebSocket) -> AuthService:
    data_layer = websocket.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _chat_service(websocket: WebSocket) -> ChatService:
    data_layer = websocket.app.state.data_layer
    return ChatService(db_path=data_layer.database_path)


def _broker(websocket: WebSocket) -> ChatRealtimeBroker:
    return websocket.app.state.realtime_broker


def _message_payload(message: dict[str, object]) -> dict[str, object]:
    return {
        "type": "chat.message",
        "message": message,
    }


def _messages_payload(messages: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "chat.history",
        "items": messages,
        "count": len(messages),
    }


def _error_payload(code: str, message: str) -> dict[str, object]:
    return {
        "type": "error",
        "error": {
            "code": code,
            "message": message,
        },
    }


def _to_message_dict(chat_message: object) -> dict[str, object]:
    from app.models import ChatMessage

    if not isinstance(chat_message, ChatMessage):
        raise TypeError("chat_message must be ChatMessage")

    return chat_message_payload(chat_message)


@router.websocket("/realtime/chat/{chat_id}")
async def realtime_chat(websocket: WebSocket, chat_id: int) -> None:
    await websocket.accept()

    session_token = (websocket.query_params.get("session_token") or "").strip()
    if not session_token:
        await websocket.send_json(_error_payload("missing_session", "session_token is required"))
        await websocket.close(code=4401)
        return

    auth_service = _auth_service(websocket)
    chat_service = _chat_service(websocket)
    broker = _broker(websocket)

    try:
        session = auth_service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        await websocket.send_json(_error_payload(exc.code, exc.message))
        await websocket.close(code=4401)
        return

    if session.user.user_id is None:
        await websocket.send_json(_error_payload("invalid_user", "Authenticated user id is missing"))
        await websocket.close(code=4401)
        return

    user_id = session.user.user_id

    try:
        _ = chat_service.list_messages(
            chat_id=chat_id,
            requester_user_id=user_id,
            limit=1,
            offset=0,
        )
    except ChatError as exc:
        await websocket.send_json(_error_payload(exc.code, exc.message))
        await websocket.close(code=4403)
        return

    await broker.connect(chat_id=chat_id, websocket=websocket)
    await websocket.send_json(
        {
            "type": "realtime.connected",
            "chat_id": chat_id,
            "user_id": user_id,
        }
    )

    try:
        while True:
            payload = await websocket.receive_json()
            event_type = str(payload.get("type", "")).strip().lower()

            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if event_type == "chat.history":
                try:
                    limit = int(payload.get("limit", 100))
                    offset = int(payload.get("offset", 0))
                except (TypeError, ValueError):
                    await websocket.send_json(
                        _error_payload("invalid_history_query", "limit and offset must be integers")
                    )
                    continue

                try:
                    messages = chat_service.list_messages(
                        chat_id=chat_id,
                        requester_user_id=user_id,
                        limit=limit,
                        offset=offset,
                    )
                except ChatError as exc:
                    await websocket.send_json(_error_payload(exc.code, exc.message))
                    continue

                await websocket.send_json(
                    _messages_payload([_to_message_dict(message) for message in messages])
                )
                continue

            if event_type == "chat.send":
                body_text = str(payload.get("body_text", ""))
                client_message_id_raw = payload.get("client_message_id")
                client_message_id = (
                    str(client_message_id_raw).strip()
                    if client_message_id_raw is not None
                    else None
                )
                if client_message_id == "":
                    client_message_id = None

                try:
                    draft = MessageDraft(
                        body_text=body_text,
                        client_message_id=client_message_id,
                    )
                    message = chat_service.send_message(
                        chat_id=chat_id,
                        author_user_id=user_id,
                        draft=draft,
                    )
                except (ChatError, ValueError) as exc:
                    if isinstance(exc, ChatError):
                        await websocket.send_json(_error_payload(exc.code, exc.message))
                    else:
                        await websocket.send_json(
                            _error_payload("invalid_message", str(exc))
                        )
                    continue

                event = chat_message_event(message)
                delivered = await broker.publish(chat_id=chat_id, event=event)
                await websocket.send_json(
                    {
                        "type": "chat.ack",
                        "message": _to_message_dict(message),
                        "delivered_to": delivered,
                    }
                )
                continue

            await websocket.send_json(
                _error_payload(
                    "unsupported_event",
                    "Supported events: ping, chat.history, chat.send",
                )
            )
    except WebSocketDisconnect:
        return
    finally:
        await broker.disconnect(chat_id=chat_id, websocket=websocket)
