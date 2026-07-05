from __future__ import annotations

from .api import ConsoleBlogGateway
from .models import BlogPostsScreenData, BlogPostView
from .presenter import build_blog_posts, parse_post_payload


class M5CardputerConsoleBlogController:
    def __init__(self, gateway: ConsoleBlogGateway) -> None:
        self._gateway = gateway

    def list_posts(
        self,
        *,
        session_token: str,
        limit: int = 20,
        offset: int = 0,
    ) -> BlogPostsScreenData:
        payload = self._gateway.list_posts(
            session_token=session_token,
            limit=limit,
            offset=offset,
        )
        return build_blog_posts(payload)

    def get_post(self, *, session_token: str, post_id: int) -> BlogPostView:
        payload = self._gateway.get_post(session_token=session_token, post_id=post_id)
        return parse_post_payload(payload)
