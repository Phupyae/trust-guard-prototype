"""Build the synthetic policy PDFs + policy_metadata.json from knowledge_base/source/*.md

Why this exists: real bank policies are authored in a word processor and published
as controlled PDFs, while their metadata (version, status, effective date) lives in
a document management system. We mimic that split:
  * source/*.md            -> what an author writes
  * knowledge_base/*.pdf   -> what gets published (and what TrustGuard reads)
  * policy_metadata.json   -> the "document management system" record

Run:  python scripts/build_pdfs.py
"""
import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "knowledge_base" / "source"
OUT_DIR = ROOT / "knowledge_base"

TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=8)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=2)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=14, spaceAfter=4)
META = ParagraphStyle("meta", fontName="Helvetica", fontSize=9, leading=11)


def parse_source(path: Path) -> tuple[dict, list[str]]:
    """Split a source file into its front-matter dict and body lines."""
    text = path.read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    meta = {}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, body.strip().splitlines()


def build_pdf(meta: dict, lines: list[str], out_path: Path) -> None:
    story = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("# "):
            story.append(Paragraph(line[2:], TITLE))
            rows = [
                ["Document ID", meta["document_id"], "Version", meta["version"]],
                ["Status", meta["status"], "Effective date", meta["effective_date"]],
                ["Owner", meta.get("owner", ""), "Classification", meta.get("classification", "")],
            ]
            table = Table([[Paragraph(c, META) for c in r] for r in rows],
                          colWidths=[28 * mm, 52 * mm, 28 * mm, 62 * mm])
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
            ]))
            story += [table, Spacer(1, 6 * mm)]
        elif line.startswith("### "):
            story.append(Paragraph(line[4:], H3))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], H2))
        else:
            story.append(Paragraph(line, BODY))

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, title=meta["title"],
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    doc.build(story)


def main() -> int:
    records = []
    for src in sorted(SOURCE_DIR.glob("*.md")):
        meta, lines = parse_source(src)
        pdf_name = src.with_suffix(".pdf").name
        build_pdf(meta, lines, OUT_DIR / pdf_name)
        records.append({
            "document_id": meta["document_id"],
            "title": meta["title"],
            "version": meta["version"],
            "status": meta["status"],
            "effective_date": meta["effective_date"],
            "expiry_date": meta.get("expiry_date"),
            "supersedes": meta.get("supersedes"),
            "superseded_by": meta.get("superseded_by"),
            "owner": meta.get("owner"),
            "file": pdf_name,
            "source_file": f"source/{src.name}",
        })
        print(f"built {pdf_name}")
    (OUT_DIR / "policy_metadata.json").write_text(json.dumps({"documents": records}, indent=2))
    print("wrote policy_metadata.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
