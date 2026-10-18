"""Typed, inspectable extraction rules. Never execute or import source examples."""
import re

from .models import EntityMention


def extract_entities(text: str, offset: int = 0) -> list[EntityMention]:
    found = []
    occupied = set()

    def add(start, end, kind, rule):
        name = text[start:end]
        if not name or len(name) > 100 or (start,end) in occupied:
            return
        occupied.add((start,end))
        found.append(EntityMention(name=name,normalized=name.removesuffix('()').lower(),kind=kind,
                                   start=offset+start,end=offset+end,rule=rule))

    for match in re.finditer(r'(?m)^\s*(?:(?:\$|>>>)\s*)?((?:pip3?|npm|pnpm|yarn|uv|poetry|docker|curl|python3?)\s+[^\r\n`]+)',text):
        add(*match.span(1),'command','command-line')
    for match in re.finditer(r'\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s`\]\)\},;]+)',text):
        add(match.start(),match.end(),'endpoint','http-method-and-path')
    for match in re.finditer(r'(?m)^\s*(?:>>>\s*)?(?:from|import)\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)',text):
        add(*match.span(1),'package','python-import')
    for match in re.finditer(r'(?m)^\s*(?:>>>\s*)?from\s+[\w.]+\s+import\s+([^\r\n]+)',text):
        for symbol in re.finditer(r'\b[A-Za-z_]\w*\b',match[1]):
            if symbol[0] not in ('as','import'):
                add(match.start(1)+symbol.start(),match.start(1)+symbol.end(),'api','imported-symbol')
    for match in re.finditer(r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?=\s*\()',text):
        if match[0] not in ('if','for','while','print','return'):
            add(*match.span(),'api','call-syntax')
    for match in re.finditer(r'(?m)^\s*@([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)',text):
        add(*match.span(1),'api','decorator')
    for match in re.finditer(r'\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b',text):
        add(*match.span(),'configuration','uppercase-setting')
    for match in re.finditer(r'\b(?:WSGI|ASGI|HTTPS?|TLS|SSL|TCP|JSON|CSV|UTF-8)\b',text):
        add(*match.span(),'protocol','known-protocol-or-format')
    for match in re.finditer(r'`{1,2}([A-Za-z_][A-Za-z0-9_.:/-]{0,97}(?:\(\))?)`{1,2}',text):
        name = match[1]
        kind = ('configuration' if re.search(r'\b(?:setting|option|variable|flag)\b',text[max(0,match.start()-35):match.end()+35],re.I)
                else 'api' if name.endswith('()') else 'identifier')
        add(*match.span(1),kind,'quoted-identifier')
    for match in re.finditer(r'\b(?:[a-z]+_[a-zA-Z0-9_]+|[a-z]+[A-Z][a-zA-Z0-9]*)\b',text):
        add(*match.span(),'identifier','identifier-shape')
    # Most specific earlier rule wins for an overlapping mention.
    chosen = []
    for row in found:
        if not any(row.start < other.end and other.start < row.end for other in chosen):
            chosen.append(row)
        if len(chosen) == 60:
            break
    return sorted(chosen,key=lambda row:(row.start,row.end))
