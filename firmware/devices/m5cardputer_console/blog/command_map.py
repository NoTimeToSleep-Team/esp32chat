from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsoleBlogCommand:
    command_id: str
    method: str
    path_template: str
    description: str


M5CARDPUTER_CONSOLE_BLOG_COMMANDS: tuple[ConsoleBlogCommand, ...] = (
    ConsoleBlogCommand(
        command_id="blog_posts_list",
        method="GET",
        path_template="/blog/api/posts",
        description="Read blog posts list",
    ),
    ConsoleBlogCommand(
        command_id="blog_post_get",
        method="GET",
        path_template="/blog/api/posts/{post_id}",
        description="Read single blog post",
    ),
)


def blog_command_path_set() -> set[str]:
    return {item.path_template for item in M5CARDPUTER_CONSOLE_BLOG_COMMANDS}
