#!/usr/bin/env python3
"""Build a reflowable EPUB 3 from MinerU Markdown.

The converter keeps the source wording intact, joins MinerU's paired English/Chinese
chapter headings, converts LaTeX formulae to MathML, embeds referenced local images,
and creates a real EPUB navigation document instead of a flat text export.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from ebooklib import epub
from latex2mathml.converter import convert as latex_to_mathml
from markdown_it import MarkdownIt


CHAPTER_MARKER = re.compile(
    r"(?m)^#\s+CHAPTER\s+(\d+)\s+第\s*\1\s*章[ \t]*$\n+^#{1,2}[ \t]+(.+?)[ \t]*$"
)
CHAPTER_BARE = re.compile(r"(?m)^#\s+第\s*(\d+)\s*章[ \t]*$\n(?:[ \t]*\n)*^##[ \t]+(.+?)[ \t]*$")
CHAPTER_START = re.compile(r"(?m)^#[ \t]+第\s*(\d+)\s*章(?:[ \t]+([^\n]+))?[ \t]*$")
TOC_CHAPTER = re.compile(r"(?m)^-\s+第\s*(\d+)\s*章\s+(.+)$")
TOC_SECTION = re.compile(r"(?m)^-\s+(\d+\.\d+)\s+(.+)$")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
DISPLAY_MATH = re.compile(r"(?m)^[ \t]*\$\$[ \t]*\n(.+?)\n[ \t]*\$\$[ \t]*$", re.DOTALL)
INLINE_MATH = re.compile(r"\$([^\n$]+)\$")


@dataclass
class Section:
    title: str
    markdown: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="MinerU Markdown file")
    parser.add_argument("output", type=Path, help="EPUB output path")
    parser.add_argument("--cover", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--isbn", required=True)
    parser.add_argument("--publisher", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--language", default="zh-CN")
    return parser.parse_args()


def normalize_chapter_headings(source: str) -> str:
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    source = CHAPTER_MARKER.sub(lambda m: f"# 第{m.group(1)}章 {m.group(2).strip()}", source)
    source = CHAPTER_BARE.sub(lambda m: f"# 第{m.group(1)}章 {m.group(2).strip()}", source)
    # MinerU marked chapter 1 explicitly in this book, but later chapter titles
    # often appear as plain level-two headings. Use the printed contents as the
    # authority for their numbering and names, without changing body text.
    contents = source.split("# 第1章", 1)[0]
    for match in TOC_CHAPTER.finditer(contents):
        number = match.group(1)
        raw_title = match.group(2).strip()
        title = re.sub(r"\s*(?:[.…]{2,}|\.{2,})\s*\d+\s*$", "", raw_title).strip()
        if not title or re.search(rf"(?m)^# 第{number}章\b", source):
            continue
        candidate = re.compile(rf"(?m)^#{{1,2}}[ \t]+{re.escape(title)}[ \t]*$")
        source = candidate.sub(f"# 第{number}章 {title}", source, count=1)
    return source


def split_sections(source: str) -> list[Section]:
    matches = list(CHAPTER_START.finditer(source))
    sections: list[Section] = []
    if not matches:
        return [Section("正文", source)]

    front = source[: matches[0].start()].strip()
    if front:
        sections.append(Section("书前", front))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        chapter_no = match.group(1)
        chapter_name = (match.group(2) or "").strip()
        title = f"第{chapter_no}章" + (f" {chapter_name}" if chapter_name else "")
        sections.append(Section(title, source[match.start() : end].strip()))
    # The references are a separate entry in the printed contents, not part
    # of chapter 14, even when the parser left them in its final page segment.
    last = sections[-1]
    references = re.search(r"(?m)^##\s+参考文献\s*$", last.markdown)
    if references:
        sections[-1] = Section(last.title, last.markdown[: references.start()].strip())
        sections.append(Section("参考文献", last.markdown[references.start() :].strip()))
    return sections


def printed_toc(source: str) -> dict[int, list[str]]:
    """Use the printed contents to exclude misclassified exercise headings."""
    front = source.split("# 第1章", 1)[0]
    result: dict[int, list[str]] = {}
    current: int | None = None
    for line in front.splitlines():
        chapter = TOC_CHAPTER.match(line)
        if chapter:
            current = int(chapter.group(1))
            result[current] = []
            continue
        section = TOC_SECTION.match(line)
        if section and current is not None and int(section.group(1).split(".")[0]) == current:
            result[current].append(section.group(1))
    return result


def plain_label(markup: str) -> str:
    label = re.sub(r"<[^>]+>", "", markup)
    return html.unescape(label).strip()


def add_navigation_targets(content: str, section: Section, allowed: list[str]) -> tuple[str, list[tuple[str, str]]]:
    """Add stable anchors to actual chapter headings present in the printed TOC."""
    found: list[tuple[str, str]] = []
    remaining = set(allowed)

    def heading(match: re.Match[str]) -> str:
        title = plain_label(match.group(1))
        number = re.match(r"^(\d+\.\d+)(?!\d)", title)
        if number and number.group(1) in remaining:
            key = number.group(1)
            remaining.remove(key)
            anchor = "sec-" + key.replace(".", "-")
            source_heading = re.search(rf"(?m)^##\s+{re.escape(key)}\s+(.+?)\s*$", section.markdown)
            label = f"{key} {source_heading.group(1).replace('$', '')}" if source_heading else title
            found.append((anchor, label))
            return f'<h2 id="{anchor}">{match.group(1)}</h2>'
        if title == "习题" and "习题" not in {label for _, label in found}:
            found.append(("exercises", title))
            return f'<h2 id="exercises" class="exercises-title">{match.group(1)}</h2>'
        return match.group(0)

    content = re.sub(r"<h2>(.*?)</h2>", heading, content, flags=re.DOTALL)
    if remaining:
        raise ValueError(f"{section.title}: printed TOC sections without body heading: {', '.join(sorted(remaining))}")
    if allowed and not any(anchor == "exercises" for anchor, _ in found):
        raise ValueError(f"{section.title}: printed TOC exercises heading missing")
    return content, found


def style_semantic_blocks(content: str) -> str:
    """Associate adjacent captions with their figure/table and emphasize labels."""

    def figure(match: re.Match[str]) -> str:
        caption = match.group(2)
        if not re.match(r"^图\s*\d+\s*[-–]\s*\d+", plain_label(caption)):
            return match.group(0)
        image = re.sub(r' alt=""', f' alt="{html.escape(plain_label(caption), quote=True)}"', match.group(1), count=1)
        return f'<figure class="book-figure">{image}<figcaption>{caption}</figcaption></figure>'

    content = re.sub(r"<p>(<img\b[^>]*?/>)</p>\s*<p>([^<]*?)</p>", figure, content)

    def table(match: re.Match[str]) -> str:
        caption = match.group(1)
        if not re.match(r"^表\s*\d+\s*[-–]\s*\d+", plain_label(caption)):
            return match.group(0)
        return f'<table class="book-table"><caption>{caption}</caption>'

    content = re.sub(r"<p>([^<]*?)</p>\s*<table>", table, content)

    def loose_caption(match: re.Match[str]) -> str:
        label = plain_label(match.group(1))
        if len(label) > 80 or any(mark in label for mark in "。！？:："):
            return match.group(0)
        if re.match(r"^图\s*\d+\s*[-–]\s*\d+", label):
            return f'<p class="figure-caption">{match.group(1)}</p>'
        if re.match(r"^表\s*\d+\s*[-–]\s*\d+", label):
            return f'<p class="table-caption">{match.group(1)}</p>'
        return match.group(0)

    content = re.sub(r"<p>([^<]*?)</p>", loose_caption, content)

    def example(match: re.Match[str]) -> str:
        return f'<p class="example-lead"><strong class="example-label">{match.group(1)}</strong>'

    content = re.sub(r"<p>(例\s*\d+\s*[-–]\s*\d+)(?!\s*(?:和|与|及|、))(?=\s|（|\()", example, content)
    return content


def math_to_placeholders(source: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str], display: bool) -> str:
        token = f"MATHPLACEHOLDER{len(replacements):06d}TOKEN"
        expression = match.group(1).strip()
        # A right brace used alone in a table cell is often emitted as an
        # unmatched \left\}; keep the brace while removing only its sizing.
        expression = expression.replace(r"\left\}", r"\}")
        try:
            markup = latex_to_mathml(expression)
            if display:
                markup = f'<div class="math-display">{markup}</div>'
            else:
                markup = f'<span class="math-inline">{markup}</span>'
        except Exception:
            delimiter = "$$" if display else "$"
            markup = f'<code class="math-source">{html.escape(delimiter + expression + delimiter)}</code>'
        replacements[token] = markup
        return token

    source = DISPLAY_MATH.sub(lambda m: replace(m, True), source)
    source = INLINE_MATH.sub(lambda m: replace(m, False), source)
    return source, replacements


def embed_images(
    book: epub.EpubBook,
    source: str,
    base_dir: Path,
    image_registry: dict[str, str],
) -> str:
    def replace(match: re.Match[str]) -> str:
        alt, raw_target = match.groups()
        target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
        if target.startswith("data:image/") and ";base64," in target:
            descriptor, encoded = target.split(",", 1)
            media_type = descriptor[5:].split(";", 1)[0]
            data = base64.b64decode(encoded)
            key = "data:" + hashlib.sha256(data).hexdigest()
            if key not in image_registry:
                extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/svg+xml": ".svg"}.get(media_type, ".bin")
                internal = f"images/figure_{len(image_registry) + 1:04d}{extension}"
                book.add_item(epub.EpubItem(uid=f"figure_{len(image_registry) + 1:04d}", file_name=internal, media_type=media_type, content=data))
                image_registry[key] = "../" + internal
            return f"![{alt}]({image_registry[key]})"
        if re.match(r"^[a-z]+://", target, re.IGNORECASE):
            return match.group(0)
        path = (base_dir / target).resolve()
        if not path.is_file():
            return match.group(0)
        key = str(path)
        if key not in image_registry:
            suffix = path.suffix.lower() or ".bin"
            internal = f"images/figure_{len(image_registry) + 1:04d}{suffix}"
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            book.add_item(epub.EpubItem(uid=f"figure_{len(image_registry) + 1:04d}", file_name=internal, media_type=media_type, content=path.read_bytes()))
            image_registry[key] = "../" + internal
        return f"![{alt}]({image_registry[key]})"

    return IMAGE.sub(replace, source)


def render_markdown(markdown: str) -> tuple[str, bool]:
    protected, replacements = math_to_placeholders(markdown)
    renderer = MarkdownIt("commonmark", {"html": True, "typographer": True}).enable("table")
    rendered = renderer.render(protected)
    for token, markup in replacements.items():
        rendered = rendered.replace(token, markup)
    return rendered, bool(replacements)


def main() -> None:
    args = parse_args()
    if args.input.is_dir():
        source = "\n\n".join(
            part.read_text(encoding="utf-8").strip()
            for part in sorted(args.input.glob("pages-*.md"))
        )
    else:
        source = args.input.read_text(encoding="utf-8")
    source = normalize_chapter_headings(source)
    toc_sections = printed_toc(source)
    sections = split_sections(source)
    print("Chapter headings:", ", ".join(section.title for section in sections[1:]))

    book = epub.EpubBook()
    book.set_identifier(f"urn:isbn:{args.isbn}" if args.isbn else f"urn:uuid:{uuid.uuid4()}")
    book.set_title(args.title)
    book.set_language(args.language)
    book.add_author(args.author)
    if args.publisher:
        book.add_metadata("DC", "publisher", args.publisher)
    if args.date:
        book.add_metadata("DC", "date", args.date)
    if args.isbn:
        book.add_metadata("DC", "identifier", args.isbn, {"id": "isbn"})

    cover_page = None
    if args.cover and args.cover.is_file():
        book.set_cover("images/cover.jpg", args.cover.read_bytes(), create_page=True)
        cover_page = book.get_item_with_id("cover")
        cover_page.is_linear = True

    css = """
body { font-family: serif; line-height: 1.7; margin: 4%; }
h1 { margin: 1.6em 0 1em; text-align: center; page-break-before: always; }
h2 { margin: 1.5em 0 .7em; padding-bottom: .2em; border-bottom: 1px solid #999; page-break-after: avoid; }
h3 { margin: 1.25em 0 .6em; page-break-after: avoid; }
p { margin: .55em 0; line-height: 1.7; text-align: justify; text-indent: 2em; }
li p, td p, th p { text-indent: 0; }
img { display: block; max-width: 100%; height: auto; margin: 1em auto; }
.book-figure { margin: 1.2em auto; text-align: center; page-break-inside: avoid; }
.book-figure img { margin: 0 auto .35em; }
.book-figure figcaption { text-align: center; font-size: .9em; line-height: 1.45; }
.figure-caption { text-align: center; text-indent: 0; font-size: .9em; line-height: 1.45; }
table { border-collapse: collapse; margin: 1em auto; max-width: 100%; font-size: .9em; }
table caption { caption-side: top; text-align: center; font-weight: bold; line-height: 1.45; margin-bottom: .4em; }
.table-caption { text-align: center; text-indent: 0; font-weight: bold; line-height: 1.45; }
th, td { border: 1px solid #888; padding: .3em .45em; vertical-align: top; }
th { text-align: center; }
.example-lead { margin-top: 1em; text-indent: 0; }
.example-label { font-weight: bold; }
.math-display { overflow-x: auto; text-align: center; margin: 1em 0; }
.math-inline { white-space: nowrap; }
.math-source { white-space: pre-wrap; }
""".strip()
    style = epub.EpubItem(uid="style", file_name="styles/book.css", media_type="text/css", content=css.encode("utf-8"))
    book.add_item(style)

    image_registry: dict[str, str] = {}
    chapters: list[epub.EpubHtml] = []
    navigation: list[object] = []
    for index, section in enumerate(sections, start=1):
        with_images = embed_images(book, section.markdown, args.input.parent, image_registry)
        content, has_math = render_markdown(with_images)
        chapter_number = re.match(r"第(\d+)章", section.title)
        targets: list[tuple[str, str]] = []
        if chapter_number:
            content, targets = add_navigation_targets(content, section, toc_sections.get(int(chapter_number.group(1)), []))
        content = style_semantic_blocks(content)
        chapter = epub.EpubHtml(
            title=section.title,
            file_name=f"text/section_{index:03d}.xhtml",
            lang=args.language,
        )
        chapter.content = content
        chapter.add_link(href="../styles/book.css", rel="stylesheet", type="text/css")
        if has_math:
            chapter.properties.append("mathml")
        book.add_item(chapter)
        chapters.append(chapter)
        if targets:
            child_links = tuple(
                epub.Link(f"{chapter.file_name}#{anchor}", label, f"nav-{index}-{anchor}")
                for anchor, label in targets
            )
            navigation.append((chapter, child_links))
        else:
            navigation.append(chapter)

    book.toc = tuple(navigation)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ([cover_page] if cover_page is not None else []) + ["nav", *chapters]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(args.output), book, {"epub3_pages": False})
    print(f"Created {args.output}")
    print(f"Sections: {len(chapters)}; printed-TOC subentries: {sum(len(item[1]) for item in navigation if isinstance(item, tuple))}; embedded images: {len(image_registry)}")


if __name__ == "__main__":
    main()
