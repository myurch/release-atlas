"""Structural Markdown/reStructuredText passages with exact Unicode source offsets."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    kind: str
    headings: tuple[str, ...]


HEADING = re.compile(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$')
UNDERLINE = re.compile(r'^\s*([=~^`:#*+\-])\1{2,}\s*$')
FENCE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')
BULLET = re.compile(r'^\s*(?:[-+*]|\d+[.)])\s+')
DEFINITION = re.compile(r'^\s*(?:\[[^\]]+\]:|\.\.\s+_[^:]+:)')
# Unformatted release notes frequently contain one complete statement per line.
RELEASE_LINE = re.compile(r'^(?:Removed|Deprecated|Added|Fixed|Corrected|Introduced|The `|Use `)')


def parse_document(text: str) -> list[Block]:
    lines = text.splitlines(keepends=True)
    offsets = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    blocks = []
    headings: list[str] = []
    rst_levels: dict[str, int] = {}

    def emit(first, last, kind):
        while last > first and not lines[last].strip():
            last -= 1
        start, end = offsets[first], offsets[last]+len(lines[last].rstrip('\r\n'))
        # Preserve all interior whitespace/line endings; only trim block edges.
        if kind not in ('code','table'):
            start += len(text[start:end])-len(text[start:end].lstrip())
            end -= len(text[start:end])-len(text[start:end].rstrip())
        if start < end:
            # Large prose is split at sentence/space boundaries, never code/tables.
            while kind in ('paragraph','list-item') and end-start > 1800:
                cut = max(text.rfind('. ',start+800,start+1800),text.rfind('\n',start+800,start+1800))
                if cut < start+800:
                    cut = text.rfind(' ',start+800,start+1800)
                if cut < start+800:
                    cut = start+1800
                elif text[cut] == '.':
                    cut += 1
                blocks.append(Block(start,cut,kind,tuple(headings)))
                start = cut
                while start < end and text[start].isspace():
                    start += 1
            blocks.append(Block(start,end,kind,tuple(headings)))

    def set_heading(level, title):
        del headings[level:]
        headings.append(title.strip()[:160])
        del headings[:-8]

    i = 0
    while i < len(lines):
        raw = lines[i].rstrip('\r\n')
        stripped = raw.strip()
        if not stripped or DEFINITION.match(raw) or re.fullmatch(r'\s*!\[[^\]]*\]\([^)]*\)\s*',raw):
            i += 1
            continue
        heading = HEADING.match(raw)
        if heading:
            set_heading(len(heading[1])-1,heading[2])
            i += 1
            continue
        if i+1 < len(lines) and UNDERLINE.match(lines[i+1]) and len(lines[i+1].strip()) >= 3:
            marker = lines[i+1].strip()[0]
            # Markdown setext and RST headings both use underline adornments.
            level = rst_levels.setdefault(marker,len(rst_levels))
            set_heading(level,stripped)
            i += 2
            continue
        if UNDERLINE.match(raw):
            i += 1
            continue
        fence = FENCE.match(raw)
        if fence:
            first = i
            delimiter = fence[1]
            i += 1
            while i < len(lines):
                closing = re.fullmatch(r'\s{0,3}'+re.escape(delimiter[0])+r'{'+str(len(delimiter))+r',}\s*',lines[i].rstrip('\r\n'))
                i += 1
                if closing:
                    break
            emit(first,i-1,'code')
            continue
        if re.match(r'^\s*\.\.\s+(?:code-block|code|sourcecode)::',raw):
            first = i
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((' ','\t'))):
                i += 1
            emit(first,i-1,'code')
            continue
        # RST literal blocks introduced by a standalone :: or indented code.
        if raw.startswith(('    ','\t')) and not BULLET.match(raw):
            first = i
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(('    ','\t'))):
                i += 1
            emit(first,i-1,'code')
            continue
        if re.match(r'^\s*(?:\|.*\||\+[-=+]+\+)\s*$',raw):
            first = i
            i += 1
            while i < len(lines) and re.match(r'^\s*(?:\|.*\||\+[-=+]+\+)\s*$',lines[i].rstrip('\r\n')):
                i += 1
            emit(first,i-1,'table')
            continue
        first = i
        kind = 'list-item' if BULLET.match(raw) else 'paragraph'
        i += 1
        while i < len(lines) and lines[i].strip():
            line = lines[i]
            if (HEADING.match(line) or FENCE.match(line) or BULLET.match(line) or DEFINITION.match(line)
                    or line.lstrip().startswith('.. ') or line.lstrip().startswith('|')
                    or (i+1 < len(lines) and UNDERLINE.match(lines[i+1]))):
                break
            if kind == 'list-item' and not line.startswith((' ','\t')):
                break
            if kind == 'paragraph' and RELEASE_LINE.match(line) and lines[i-1].rstrip().endswith(('.',';')):
                break
            i += 1
        emit(first,i-1,kind)
    return blocks
