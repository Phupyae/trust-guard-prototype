"""Load policy documents and split them into citable sections.

Why split by section instead of fixed-size chunks? Policies are already organised
into numbered sections, each covering one rule. Splitting on those boundaries means
every chunk is one coherent rule AND carries its own citation ("Section 4.2") for free.

How headings are detected in a PDF: a line is a heading only if it is BOLD *and*
starts with a section number ("4.2 Daily Allowance"). Requiring both prevents body
text that happens to start with a number ("30 calendar days...") from being mistaken
for a heading.
"""
import json
import re
from pathlib import Path

import pymupdf

import config
from modules.schemas import Chunk

HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
BOLD_FLAG = 16  # PyMuPDF span flag bit for bold text


def load_metadata(path: Path = config.METADATA_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["documents"]


def _pdf_lines(pdf_path: Path) -> list[tuple[str, bool]]:
    """Return (text, is_bold) for every text line in the PDF, in reading order."""
    lines = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    spans = [s for s in line["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    text = " ".join(s["text"].strip() for s in spans)
                    bold = all(s["flags"] & BOLD_FLAG or "Bold" in s["font"] for s in spans)
                    lines.append((text, bold))
    return lines


def _md_lines(md_path: Path) -> list[tuple[str, bool]]:
    """Markdown fallback: '#'-headings count as bold, front matter is skipped."""
    text = md_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if raw:
            is_heading = raw.startswith("#")
            lines.append((raw.lstrip("#").strip(), is_heading))
    return lines


def _split_sections(lines: list[tuple[str, bool]]) -> list[tuple[str, str, str]]:
    """Group lines into (section_number, section_title, body). Sections with no body
    (e.g. '4 Allowances' that only contains sub-sections) are dropped."""
    sections, current, body = [], None, []
    for text, bold in lines:
        match = HEADING_RE.match(text)
        if bold and match:
            if current and body:
                sections.append((*current, " ".join(body)))
            current, body = (match.group(1), match.group(2)), []
        elif current:
            body.append(text)
        # lines before the first numbered heading (title, metadata table) are ignored
    if current and body:
        sections.append((*current, " ".join(body)))
    return sections


def load_document(meta: dict, prefer: str = "pdf") -> list[Chunk]:
    kb = config.KNOWLEDGE_BASE_DIR
    pdf_path, md_path = kb / meta["file"], kb / meta["source_file"]
    if prefer == "pdf" and pdf_path.exists():
        lines = _pdf_lines(pdf_path)
    elif md_path.exists():
        lines = _md_lines(md_path)
    else:
        raise FileNotFoundError(f"No PDF or source file for {meta['document_id']}")

    return [
        Chunk(
            chunk_id=f"{meta['document_id']}::{num}",
            document_id=meta["document_id"],
            document_title=meta["title"],
            version=meta["version"],
            status=meta["status"],
            effective_date=meta["effective_date"],
            section=num,
            section_title=title,
            text=body,
        )
        for num, title, body in _split_sections(lines)
    ]


def load_knowledge_base(prefer: str = "pdf") -> list[Chunk]:
    """Load every document listed in policy_metadata.json."""
    chunks = []
    for meta in load_metadata():
        chunks.extend(load_document(meta, prefer=prefer))
    return chunks


if __name__ == "__main__":
    for c in load_knowledge_base():
        print(f"[{c.status:10}] {c.chunk_id:28} {c.section_title:28} | {c.text[:60]}")
