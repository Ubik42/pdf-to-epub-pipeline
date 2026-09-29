#!/usr/bin/env python3
"""Check coverage and packaging of a segmented MinerU-to-EPUB conversion."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path

from ebooklib import ITEM_DOCUMENT, ITEM_IMAGE, epub
from lxml import etree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path)
    parser.add_argument("epub", type=Path)
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--epubcheck", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    job = tomllib.loads(args.job.read_text(encoding="utf-8"))
    expected_pages = job["source"]["pages"]
    expected_hash = job["source"]["sha256"].lower()
    segment_info = sorted(args.segments.glob("pages-*.json"))
    coverage: list[int] = []
    segment_errors: list[str] = []
    for info_path in segment_info:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        first, last = info["pages"]
        coverage.extend(range(first, last + 1))
        md = info_path.with_suffix(".md")
        if info["source_sha256"].lower() != expected_hash or not md.is_file():
            segment_errors.append(info_path.name)
    coverage_ok = coverage == list(range(1, expected_pages + 1))

    book = epub.read_epub(str(args.epub))
    documents = [item for item in book.get_items_of_type(ITEM_DOCUMENT)]
    images = [item for item in book.get_items_of_type(ITEM_IMAGE)]
    all_markup = b"\n".join(item.get_content() for item in documents)
    content = all_markup.decode("utf-8", errors="replace")
    chapter_links = re.findall(r">第\s*\d+\s*章[^<]*<", content)
    structural_errors = []
    if "data:image/" in content:
        structural_errors.append("embedded_data_uri")
    if "MATHPLACEHOLDER" in content:
        structural_errors.append("unreplaced_math_placeholder")
    if len(book.spine) < 3:
        structural_errors.append("short_spine")
    nav = next((item for item in documents if item.file_name.endswith("nav.xhtml")), None)
    toc_links = []
    if nav is None:
        structural_errors.append("missing_nav")
    else:
        nav_root = etree.fromstring(nav.get_content())
        toc_nodes = nav_root.xpath('//*[local-name()="nav" and @epub:type="toc"]', namespaces={"epub": "http://www.idpf.org/2007/ops"})
        if not toc_nodes:
            structural_errors.append("missing_toc")
        else:
            toc_links = toc_nodes[0].xpath('.//*[local-name()="a"]')
            for link in toc_links:
                href = link.get("href", "")
                path, _, fragment = href.partition("#")
                target_path = posixpath.normpath(posixpath.join(posixpath.dirname(nav.file_name), path))
                target = book.get_item_with_href(target_path)
                if target is None:
                    structural_errors.append(f"bad_toc_target:{href}")
                elif fragment:
                    target_root = etree.fromstring(target.get_content())
                    if not target_root.xpath('//*[@id=$anchor]', anchor=fragment):
                        structural_errors.append(f"bad_toc_anchor:{href}")
    with zipfile.ZipFile(args.epub) as archive:
        bad_member = archive.testzip()
    if bad_member:
        structural_errors.append(f"bad_zip_member:{bad_member}")

    result = subprocess.run(
        [str(args.java), "-jar", str(args.epubcheck), str(args.epub)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    epubcheck_text = (result.stdout + "\n" + result.stderr).strip()
    report = {
        "job": job["id"],
        "source_pages": expected_pages,
        "segments": len(segment_info),
        "coverage_ok": coverage_ok,
        "segment_errors": segment_errors,
        "spine_items": len(book.spine),
        "documents": len(documents),
        "images": len(images),
        "chapter_mentions": len(chapter_links),
        "toc_links": len(toc_links),
        "figures_with_captions": content.count("<figcaption>"),
        "tables_with_captions": content.count("<caption>"),
        "structural_errors": structural_errors,
        "epubcheck_exit_code": result.returncode,
        "epubcheck_output": epubcheck_text,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if coverage_ok and not segment_errors and not structural_errors and result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
