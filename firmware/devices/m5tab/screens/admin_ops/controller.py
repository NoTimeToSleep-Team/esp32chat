from __future__ import annotations

from .api import AdminOpsGateway
from .models import (
    AdminModeStateView,
    BlogPostView,
    BlogPostsScreenData,
    RfidCardView,
    RfidCardsScreenData,
    SupportMessageView,
    SupportTicketView,
    SupportTicketsScreenData,
)
from .presenter import (
    build_blog_posts_screen,
    build_rfid_cards_screen,
    build_support_tickets_screen,
    parse_blog_post,
    parse_mode_state,
    parse_rfid_card,
    parse_support_message,
    parse_support_ticket,
)


class M5TabAdminOpsController:
    def __init__(self, gateway: AdminOpsGateway) -> None:
        self._gateway = gateway

    def list_support_tickets(
        self,
        *,
        session_token: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SupportTicketsScreenData:
        payload = self._gateway.list_support_tickets(
            session_token=session_token,
            status=status,
            limit=limit,
            offset=offset,
        )
        return build_support_tickets_screen(payload, status_filter=status)

    def reply_support_ticket(
        self,
        *,
        session_token: str,
        ticket_id: int,
        body_text: str,
    ) -> SupportMessageView:
        payload = self._gateway.reply_support_ticket(
            session_token=session_token,
            ticket_id=ticket_id,
            body_text=body_text,
        )
        return self._extract_support_message(payload, operation="reply_support_ticket")

    def set_support_ticket_status(
        self,
        *,
        session_token: str,
        ticket_id: int,
        status: str,
    ) -> SupportTicketView:
        payload = self._gateway.set_support_ticket_status(
            session_token=session_token,
            ticket_id=ticket_id,
            status=status,
        )
        return self._extract_support_ticket(payload, operation="set_support_ticket_status")

    def list_blog_posts(
        self,
        *,
        session_token: str,
        limit: int = 50,
        offset: int = 0,
    ) -> BlogPostsScreenData:
        payload = self._gateway.list_blog_posts(session_token=session_token, limit=limit, offset=offset)
        return build_blog_posts_screen(payload)

    def publish_blog_post(
        self,
        *,
        session_token: str,
        title: str,
        body_text: str,
    ) -> BlogPostView:
        payload = self._gateway.publish_blog_post(
            session_token=session_token,
            title=title,
            body_text=body_text,
        )
        return self._extract_blog_post(payload, operation="publish_blog_post")

    def list_rfid_cards(
        self,
        *,
        session_token: str,
        include_inactive: bool = True,
        limit: int = 200,
        offset: int = 0,
    ) -> RfidCardsScreenData:
        payload = self._gateway.list_rfid_cards(
            session_token=session_token,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )
        return build_rfid_cards_screen(payload)

    def enroll_rfid_card(
        self,
        *,
        session_token: str,
        card_uid: str,
        card_label: str,
        note: str | None = None,
        is_active: bool = True,
    ) -> RfidCardView:
        payload = self._gateway.enroll_rfid_card(
            session_token=session_token,
            card_uid=card_uid,
            card_label=card_label,
            note=note,
            is_active=is_active,
        )
        return self._extract_rfid_card(payload, operation="enroll_rfid_card")

    def set_rfid_card_active(
        self,
        *,
        session_token: str,
        card_id: int,
        is_active: bool,
    ) -> RfidCardView:
        payload = self._gateway.set_rfid_card_active(
            session_token=session_token,
            card_id=card_id,
            is_active=is_active,
        )
        return self._extract_rfid_card(payload, operation="set_rfid_card_active")

    def get_mode_state(self, *, session_token: str) -> AdminModeStateView:
        payload = self._gateway.get_mode_state(session_token=session_token)
        return parse_mode_state(payload)

    def set_mode_with_safe_hold(
        self,
        *,
        session_token: str,
        access_mode: str,
        hold_seconds: int | None = None,
    ) -> AdminModeStateView:
        state = self.get_mode_state(session_token=session_token)
        effective_hold = state.required_hold_seconds if hold_seconds is None else hold_seconds
        if effective_hold < state.required_hold_seconds:
            effective_hold = state.required_hold_seconds

        payload = self._gateway.set_mode(
            session_token=session_token,
            access_mode=access_mode,
            hold_seconds=effective_hold,
        )
        return parse_mode_state(payload)

    @staticmethod
    def _extract_support_ticket(payload: dict[str, object], *, operation: str) -> SupportTicketView:
        if payload.get("status") != "ok":
            raise RuntimeError(f"{operation} returned unexpected status")
        ticket_payload = payload.get("ticket")
        if not isinstance(ticket_payload, dict):
            raise RuntimeError(f"{operation} payload.ticket must be object")
        return parse_support_ticket(ticket_payload)

    @staticmethod
    def _extract_support_message(payload: dict[str, object], *, operation: str) -> SupportMessageView:
        if payload.get("status") != "ok":
            raise RuntimeError(f"{operation} returned unexpected status")
        message_payload = payload.get("message")
        if not isinstance(message_payload, dict):
            raise RuntimeError(f"{operation} payload.message must be object")
        return parse_support_message(message_payload)

    @staticmethod
    def _extract_blog_post(payload: dict[str, object], *, operation: str) -> BlogPostView:
        if payload.get("status") != "ok":
            raise RuntimeError(f"{operation} returned unexpected status")
        post_payload = payload.get("post")
        if not isinstance(post_payload, dict):
            raise RuntimeError(f"{operation} payload.post must be object")
        return parse_blog_post(post_payload)

    @staticmethod
    def _extract_rfid_card(payload: dict[str, object], *, operation: str) -> RfidCardView:
        if payload.get("status") != "ok":
            raise RuntimeError(f"{operation} returned unexpected status")
        card_payload = payload.get("card")
        if not isinstance(card_payload, dict):
            raise RuntimeError(f"{operation} payload.card must be object")
        return parse_rfid_card(card_payload)
