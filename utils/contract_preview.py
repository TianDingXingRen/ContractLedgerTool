"""Build a lightweight live-preview model from a DOCX contract template."""

from __future__ import annotations

from collections import defaultdict
import logging
import os
import re
from typing import Any

from docx import Document
from docx.oxml.ns import qn


MARKER_RE = re.compile(r'\{\{?(.+?)\}\}?')
MAX_PARAGRAPHS = 260
MAX_TABLE_ROWS = 80
MAX_TABLE_COLS = 14
MAX_CELL_TEXT = 800

_log = logging.getLogger('contract_tool')


def build_preview_model(source_docx: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Return paragraph/table blocks plus non-fatal warnings for live preview.

    The model is intentionally small and HTML-agnostic. It preserves the DOCX body order
    and maps marker occurrences to concrete field ids where possible.
    """
    if not source_docx or not os.path.exists(source_docx):
        return {
            'blocks': [],
            'warnings': ['模板源文件不存在，已切换为字段预览。'],
        }

    try:
        doc = Document(source_docx)
    except Exception:
        _log.warning('Failed to parse contract preview source: %s', source_docx, exc_info=True)
        return {
            'blocks': [],
            'warnings': ['模板源文件无法解析，已切换为字段预览。'],
        }

    index = _build_field_index(fields)
    blocks: list[dict[str, Any]] = []
    warnings: list[str] = []
    paragraph_index = 0
    table_index = 0
    paragraphs_truncated = False

    for child in doc.element.body:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == 'p':
            if paragraph_index < MAX_PARAGRAPHS:
                text = _xml_text(child)
                parts = _parts_for_text(text, index['paragraph'].get(paragraph_index, {}))
                blocks.append({
                    'type': 'paragraph',
                    'paragraph_index': paragraph_index,
                    'parts': parts,
                    'field_ids': _field_ids(parts),
                    'align': _paragraph_alignment(child),
                    'style': _paragraph_style(child),
                    'format': _paragraph_format(child),
                    'empty': not text.strip(),
                })
            else:
                paragraphs_truncated = True
            paragraph_index += 1
        elif tag == 'tbl':
            block = _table_block(child, table_index, index)
            warnings.extend(block.pop('_warnings', []))
            blocks.append(block)
            table_index += 1

    if paragraphs_truncated:
        warnings.append(f'合同段落超过 {MAX_PARAGRAPHS} 段，实时预览已截断后续段落。')

    return {
        'blocks': blocks,
        'warnings': warnings,
    }


def build_preview_blocks(source_docx: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Backward-compatible block-only preview API."""
    return build_preview_model(source_docx, fields).get('blocks', [])


def _build_field_index(fields: list[dict[str, Any]]) -> dict[str, Any]:
    paragraph: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    table_cell: dict[tuple[int, int, int], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    repeat_tables: dict[int, dict[str, Any]] = {}

    for field in fields or []:
        location = field.get('location') or {}
        loc_type = location.get('type')
        placeholder = str(location.get('placeholder') or '')
        if loc_type == 'paragraph':
            paragraph[int(location.get('body_index', -1))][placeholder].append(field)
        elif loc_type == 'table_cell':
            key = (
                int(location.get('table_index', -1)),
                int(location.get('row_index', -1)),
                int(location.get('col_index', -1)),
            )
            table_cell[key][placeholder].append(field)
        elif loc_type == 'table':
            table_index = int(location.get('table_index', -1))
            if table_index >= 0:
                repeat_tables[table_index] = field

    return {
        'paragraph': paragraph,
        'table_cell': table_cell,
        'repeat_tables': repeat_tables,
    }


def _table_block(table_elem, table_index: int, index: dict[str, Any]) -> dict[str, Any]:
    repeat_field = index['repeat_tables'].get(table_index)
    repeat_row_index = None
    if repeat_field:
        repeat_row_index = int((repeat_field.get('location') or {}).get('template_row_index', -1))

    rows = []
    warnings: list[str] = []
    source_rows = table_elem.findall(qn('w:tr'))
    if len(source_rows) > MAX_TABLE_ROWS:
        warnings.append(f'第 {table_index + 1} 个表格超过 {MAX_TABLE_ROWS} 行，实时预览已截断后续行。')
    truncated_cols = False
    truncated_text = False
    for row_index, row in enumerate(source_rows[:MAX_TABLE_ROWS]):
        cells = []
        source_cells = row.findall(qn('w:tc'))
        if len(source_cells) > MAX_TABLE_COLS:
            truncated_cols = True
        for col_index, cell in enumerate(source_cells[:MAX_TABLE_COLS]):
            raw_text = _xml_text(cell)
            if len(raw_text) > MAX_CELL_TEXT:
                truncated_text = True
            text = raw_text[:MAX_CELL_TEXT]
            if repeat_field and row_index == repeat_row_index:
                parts = _repeat_cell_parts(text, repeat_field, col_index)
            else:
                cell_key = (table_index, row_index, col_index)
                parts = _parts_for_text(text, index['table_cell'].get(cell_key, {}))
            cells.append({
                'parts': parts,
                'field_ids': _field_ids(parts),
                'col_span': _cell_col_span(cell),
                'format': _cell_format(cell),
            })
        rows.append({
            'row_index': row_index,
            'repeat_field_id': repeat_field.get('id') if repeat_field and row_index == repeat_row_index else None,
            'cells': cells,
        })

    if truncated_cols:
        warnings.append(f'第 {table_index + 1} 个表格存在超过 {MAX_TABLE_COLS} 列的行，实时预览已截断多余列。')
    if truncated_text:
        warnings.append(f'第 {table_index + 1} 个表格存在超长单元格，实时预览仅显示前 {MAX_CELL_TEXT} 个字符。')

    return {
        'type': 'table',
        'table_index': table_index,
        'field_ids': [repeat_field.get('id')] if repeat_field and repeat_field.get('id') is not None else [],
        'grid': _table_grid(table_elem),
        'align': _table_alignment(table_elem),
        'rows': rows,
        '_warnings': warnings,
    }


def _parts_for_text(text: str, fields_by_placeholder: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if not text:
        return []

    parts: list[dict[str, Any]] = []
    cursor = 0
    used_counts: dict[str, int] = defaultdict(int)

    for match in MARKER_RE.finditer(text):
        if match.start() > cursor:
            parts.append({'kind': 'text', 'text': text[cursor:match.start()]})

        marker = match.group(0)
        field = _match_field(marker, match.group(1).strip(), fields_by_placeholder, used_counts)
        if field:
            parts.append({
                'kind': 'field',
                'field_id': field.get('id'),
                'label': field.get('label') or field.get('key') or match.group(1).strip(),
                'placeholder': marker,
            })
        else:
            parts.append({'kind': 'text', 'text': marker})
        cursor = match.end()

    if cursor < len(text):
        parts.append({'kind': 'text', 'text': text[cursor:]})
    return parts


def _match_field(marker: str, marker_name: str, fields_by_placeholder: dict[str, list[dict[str, Any]]], used_counts: dict[str, int]):
    candidates = fields_by_placeholder.get(marker) or []
    marker_key = marker
    if not candidates:
        marker_key = f'__fallback__:{marker_name}'
        candidates = [
            field
            for field_list in fields_by_placeholder.values()
            for field in field_list
            if marker_name in {str(field.get('label') or ''), str(field.get('key') or '')}
        ]
    if not candidates:
        return None
    index = used_counts[marker_key]
    used_counts[marker_key] += 1
    if index < len(candidates):
        return candidates[index]
    return candidates[-1]


def _repeat_cell_parts(text: str, repeat_field: dict[str, Any], col_index: int) -> list[dict[str, Any]]:
    columns = repeat_field.get('columns') or []
    col = columns[col_index] if col_index < len(columns) else {}
    col_key = col.get('key') or f'col_{col_index}'
    col_label = col.get('label') or col_key

    if not text:
        return [{'kind': 'row_index'}] if _is_index_column(col, col_index) else []

    parts: list[dict[str, Any]] = []
    cursor = 0
    replaced = False
    for match in MARKER_RE.finditer(text):
        if match.start() > cursor:
            parts.append({'kind': 'text', 'text': text[cursor:match.start()]})
        if not replaced:
            parts.append({
                'kind': 'table_column',
                'field_id': repeat_field.get('id'),
                'column_key': col_key,
                'label': col_label,
            })
            replaced = True
        else:
            parts.append({'kind': 'text', 'text': match.group(0)})
        cursor = match.end()

    if cursor < len(text):
        parts.append({'kind': 'text', 'text': text[cursor:]})
    if not parts and _is_index_column(col, col_index):
        parts.append({'kind': 'row_index'})
    return parts


def _is_index_column(col: dict[str, Any], col_index: int) -> bool:
    label = str(col.get('label') or '').strip()
    key = str(col.get('key') or '').strip().lower()
    return col_index == 0 and (label in {'序号', '序', '编号'} or key in {'序号', 'index', 'no', 'number'})


def _field_ids(parts: list[dict[str, Any]]) -> list[Any]:
    ids = []
    for part in parts:
        field_id = part.get('field_id')
        if field_id is not None and field_id not in ids:
            ids.append(field_id)
    return ids


def _xml_text(elem) -> str:
    return ''.join(t.text or '' for t in elem.iter(qn('w:t')))


def _paragraph_alignment(para_elem) -> str:
    p_pr = para_elem.find(qn('w:pPr'))
    if p_pr is None:
        return ''
    jc = p_pr.find(qn('w:jc'))
    if jc is None:
        return ''
    return jc.get(qn('w:val'), '') or ''


def _paragraph_style(para_elem) -> str:
    p_pr = para_elem.find(qn('w:pPr'))
    if p_pr is None:
        return ''
    style = p_pr.find(qn('w:pStyle'))
    if style is None:
        return ''
    return style.get(qn('w:val'), '') or ''


def _paragraph_format(para_elem) -> dict[str, Any]:
    p_pr = para_elem.find(qn('w:pPr'))
    fmt: dict[str, Any] = {}
    if p_pr is not None:
        ind = p_pr.find(qn('w:ind'))
        if ind is not None:
            left = _twips_attr(ind, 'left')
            first = _twips_attr(ind, 'firstLine')
            hanging = _twips_attr(ind, 'hanging')
            if left is not None:
                fmt['left_indent_pt'] = round(left / 20, 2)
            if first is not None:
                fmt['first_line_indent_pt'] = round(first / 20, 2)
            elif hanging is not None:
                fmt['first_line_indent_pt'] = round(-hanging / 20, 2)
        spacing = p_pr.find(qn('w:spacing'))
        if spacing is not None:
            before = _twips_attr(spacing, 'before')
            after = _twips_attr(spacing, 'after')
            line = _twips_attr(spacing, 'line')
            if before is not None:
                fmt['space_before_pt'] = round(before / 20, 2)
            if after is not None:
                fmt['space_after_pt'] = round(after / 20, 2)
            if line is not None:
                fmt['line_pt'] = round(line / 20, 2)

    run_fmt = _first_run_format(para_elem)
    fmt.update({k: v for k, v in run_fmt.items() if v is not None})
    return fmt


def _first_run_format(elem) -> dict[str, Any]:
    for run in elem.iter(qn('w:r')):
        if not _xml_text(run).strip():
            continue
        r_pr = run.find(qn('w:rPr'))
        if r_pr is None:
            return {}
        fmt: dict[str, Any] = {}
        size = r_pr.find(qn('w:sz'))
        if size is not None:
            val = size.get(qn('w:val'))
            if val and val.isdigit():
                fmt['font_size_pt'] = round(int(val) / 2, 2)
        if r_pr.find(qn('w:b')) is not None:
            fmt['bold'] = True
        font = r_pr.find(qn('w:rFonts'))
        if font is not None:
            east_asia = font.get(qn('w:eastAsia'))
            ascii_font = font.get(qn('w:ascii'))
            if east_asia or ascii_font:
                fmt['font_family'] = east_asia or ascii_font
        return fmt
    return {}


def _cell_format(cell_elem) -> dict[str, Any]:
    fmt = _first_run_format(cell_elem)
    first_para = cell_elem.find(qn('w:p'))
    if first_para is not None:
        align = _paragraph_alignment(first_para)
        if align:
            fmt['align'] = align
    return fmt


def _cell_col_span(cell_elem) -> int:
    tc_pr = cell_elem.find(qn('w:tcPr'))
    if tc_pr is None:
        return 1
    grid_span = tc_pr.find(qn('w:gridSpan'))
    if grid_span is None:
        return 1
    val = grid_span.get(qn('w:val'))
    try:
        return max(1, int(val or '1'))
    except ValueError:
        return 1


def _table_grid(table_elem) -> list[int]:
    grid = table_elem.find(qn('w:tblGrid'))
    if grid is None:
        return []
    widths = []
    for col in grid.findall(qn('w:gridCol'))[:MAX_TABLE_COLS]:
        val = col.get(qn('w:w'))
        try:
            widths.append(max(1, int(val or '0')))
        except ValueError:
            widths.append(1)
    return widths


def _table_alignment(table_elem) -> str:
    tbl_pr = table_elem.find(qn('w:tblPr'))
    if tbl_pr is None:
        return ''
    jc = tbl_pr.find(qn('w:jc'))
    if jc is None:
        return ''
    return jc.get(qn('w:val'), '') or ''


def _twips_attr(elem, local_name: str) -> int | None:
    val = elem.get(qn(f'w:{local_name}'))
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None
