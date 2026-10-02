"""Render Markdown into native text runs without loading remote resources."""

from urllib.parse import urlsplit

from markdown_it import MarkdownIt


def safe_link(url):
    try:
        return urlsplit(url).scheme.lower() in {"http", "https", "mailto"}
    except ValueError:
        return False


def markdown_runs(text):
    """Yield (visible text, style names, optional hyperlink) for a full document."""
    tokens = MarkdownIt("commonmark", {"html": False}).enable("table").parse(text)
    styles = []
    lists = []
    for token in tokens:
        kind = token.type
        if kind == "heading_open":
            styles.append(token.tag)
        elif kind == "heading_close":
            styles.pop()
            yield "\n\n", (), None
        elif kind in {"bullet_list_open", "ordered_list_open"}:
            lists.append(None if kind == "bullet_list_open" else int(token.attrGet("start") or 1))
        elif kind in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
            if not lists:
                yield "\n", (), None
        elif kind == "list_item_open":
            number = lists[-1]
            marker = "• " if number is None else f"{number}. "
            if number is not None:
                lists[-1] += 1
            yield "  " * (len(lists) - 1) + marker, tuple(styles), None
        elif kind == "paragraph_close":
            yield "\n" if lists else "\n\n", (), None
        elif kind == "blockquote_open":
            styles.append("quote")
        elif kind == "blockquote_close":
            styles.pop()
        elif kind in {"fence", "code_block"}:
            yield token.content + "\n", ("code",), None
        elif kind == "hr":
            yield "────────────────────\n\n", (), None
        elif kind == "th_open":
            styles.append("bold")
        elif kind == "th_close":
            styles.pop()
            yield "    ", (), None
        elif kind == "td_close":
            yield "    ", (), None
        elif kind == "tr_close":
            yield "\n", (), None
        elif kind == "table_close":
            yield "\n", (), None
        elif kind == "inline":
            inline_styles = list(styles)
            links = []
            for child in token.children or []:
                if child.type in {"strong_open", "em_open", "s_open"}:
                    inline_styles.append({"strong_open": "bold", "em_open": "italic", "s_open": "strike"}[child.type])
                elif child.type in {"strong_close", "em_close", "s_close"}:
                    inline_styles.pop()
                elif child.type == "link_open":
                    target = child.attrGet("href") or ""
                    links.append(target if safe_link(target) else None)
                elif child.type == "link_close":
                    links.pop()
                elif child.type in {"softbreak", "hardbreak"}:
                    yield "\n", tuple(inline_styles), None
                elif child.type == "code_inline":
                    yield child.content, tuple(inline_styles) + ("code",), None
                elif child.type == "image":
                    yield "[Image: " + child.content + "]", tuple(inline_styles), None
                elif child.type == "text":
                    yield child.content, tuple(inline_styles), links[-1] if links else None


def render_buffer(buffer, text, Pango):
    tags = {
        "bold": {"weight": Pango.Weight.BOLD},
        "italic": {"style": Pango.Style.ITALIC},
        "strike": {"strikethrough": True},
        "code": {"family": "monospace"},
        "quote": {"style": Pango.Style.ITALIC, "left_margin": 44},
    }
    for level in range(1, 7):
        tags[f"h{level}"] = {"weight": Pango.Weight.BOLD, "scale": max(1.05, 1.9 - level * 0.15)}
    for name, props in tags.items():
        buffer.create_tag(name, **props)
    links = {}
    for content, names, target in markdown_runs(text):
        start = buffer.get_char_count()
        buffer.insert_with_tags_by_name(buffer.get_end_iter(), content, *names)
        if target:
            tag = buffer.create_tag(None, underline=Pango.Underline.SINGLE, foreground="#3584e4")
            links[tag] = target
            buffer.apply_tag(tag, buffer.get_iter_at_offset(start), buffer.get_end_iter())
    buffer.set_modified(False)
    return links
