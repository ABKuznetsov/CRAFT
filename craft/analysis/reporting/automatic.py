"""Compose frozen scientific views into numbered prose, panels and tables."""
from base64 import b64encode
from dataclasses import dataclass, replace
from html import escape

from craft.analysis.reporting.composer import ReportDraft, ReportFigure
from craft.analysis.reporting.model import Availability
from craft.analysis.reporting.catalog import ARTICLE_TABLE_IDS


@dataclass(frozen=True, slots=True)
class ComposedFigure:
    number: int
    panels: tuple[ReportFigure, ...]


def _subject(figure):
    if figure.narrative is None:
        return (figure.id,)
    return (figure.manifest.structure_fingerprint, figure.manifest.content_identity,
            figure.narrative.role, tuple(sorted(figure.narrative.subject_refs)),
            tuple(sorted(figure.manifest.visible_object_refs)))


def composed_figures(draft):
    groups = {}
    for figure in draft.figures:
        if figure.include:
            groups.setdefault(_subject(figure), []).append(figure)
    return tuple(ComposedFigure(index, tuple(panels)) for index, panels in enumerate(groups.values(), 1))


def append_report_view(draft, figure, report):
    # Selection is transient and does not create another camera/material view.
    signature = replace(figure.manifest, selected_object_refs=())
    for previous in draft.figures:
        if (previous.narrative is not None and _subject(previous) == _subject(figure)
                and replace(previous.manifest, selected_object_refs=()) == signature):
            return draft.with_figure(replace(previous, include=True)) if not previous.include else draft
    available = tuple(key for key, table in report.tables.items() if table.availability is Availability.AVAILABLE)
    requested = figure.narrative.table_ids if figure.narrative is not None else ()
    selected = tuple(dict.fromkeys((*draft.selected_table_ids,
        *(key for key in requested if key in ARTICLE_TABLE_IDS and key in available
          and report.tables[key].rows and key not in draft.suppressed_table_ids))))
    return replace(draft.with_figure(figure), available_table_ids=available, selected_table_ids=selected)


def report_paragraphs(draft):
    descriptions = {}
    table_numbers = {identifier: index for index, identifier in enumerate(draft.selected_table_ids, 1)}
    for group in composed_figures(draft):
        for panel in group.panels:
            if not panel.description.strip():
                continue
            numbers, tables = descriptions.setdefault(panel.description, ([], []))
            if group.number not in numbers:
                numbers.append(group.number)
            if panel.narrative is not None:
                for key in panel.narrative.table_ids:
                    if key in table_numbers and table_numbers[key] not in tables:
                        tables.append(table_numbers[key])
    paragraphs = []
    for text, (numbers, tables) in descriptions.items():
        reference = "Fig. " + ", ".join(map(str, numbers))
        if tables:
            reference += "; Table " + ", ".join(map(str, sorted(tables)))
        paragraphs.append(f"{text.rstrip().rstrip('.')} ({reference}).")
    return tuple(paragraphs)


def _image(figure, width):
    png = b64encode(figure.preview_png).decode("ascii")
    return f'<img width="{width}" src="data:image/png;base64,{png}" alt="{escape(figure.title, quote=True)}">'


def publication_tables(draft, report):
    """One table order, availability and author selection for all exporters."""
    for number, identifier in enumerate(draft.selected_table_ids, 1):
        table = report.tables.get(identifier)
        title = table.title if table is not None else identifier
        if table is None or table.availability is not Availability.AVAILABLE:
            reason = table.unavailable_reason if table is not None else "This table is unavailable in the current result."
            yield number, title, None, reason
        else:
            yield number, title, draft.publication_table(table), ""


def render_report_html(draft, report=None):
    """Self-contained, escaped report; only inline PNG assets, no remote URLs."""
    title = report.structure_name if report is not None else "Crystal structure"
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<style>body{font:15px/1.5 sans-serif;max-width:1000px;margin:32px auto;padding:0 18px;color:#17212b;background:#fff}'
             'img{max-width:100%;height:auto}figure{margin:24px 0;break-inside:avoid}.panels{width:100%;table-layout:fixed;border:0}'
             '.panels td{border:0;text-align:center;vertical-align:top}table{border-collapse:collapse;width:100%;margin:12px 0}'
             'th,td{border:1px solid #cbd2d9;padding:5px;text-align:left;overflow-wrap:anywhere}th{background:#edf1f4}'
             '.note{color:#646d76;font-size:90%}@media print{body{margin:0;max-width:none}thead{display:table-header-group}}</style>',
             f'<title>{escape(title)}</title></head><body><h1>{escape(title)}</h1>']
    for paragraph in report_paragraphs(draft):
        parts.append(f"<p>{escape(paragraph)}</p>")
    for group in composed_figures(draft):
        first = group.panels[0]
        parts.append(f'<figure id="{escape(first.id, quote=True)}"><table class="panels">')
        for start in range(0, len(group.panels), 2):
            chunk = group.panels[start:start + 2]
            parts.append("<tr>")
            for offset, panel in enumerate(chunk, start):
                label = chr(ord("a") + offset) if len(group.panels) > 1 else ""
                parts.append(f'<td>{_image(panel, 340 if len(group.panels) > 1 else 680)}<br>{label}</td>')
            parts.append("</tr>")
        parts.append(f"</table><figcaption><b>Figure {group.number}.</b> {escape(first.caption)}</figcaption>")
        if any(panel.stale for panel in group.panels):
            parts.append('<p class="note">This view belongs to an earlier analysis state.</p>')
        # Each panel retains its own caption and styles, including author edits.
        if len(group.panels) > 1:
            for index, panel in enumerate(group.panels):
                if panel.caption != first.caption:
                    parts.append(f'<p>{chr(ord("a") + index)}) {escape(panel.caption)}</p>')
        parts.append("</figure>")
    if report is not None:
        for number, title, table, reason in publication_tables(draft, report):
            parts.append(f'<h3>Table {number}. {escape(title)}</h3>')
            if table is None:
                parts.append(f'<p class="note">{escape(reason)}</p>')
                continue
            columns = tuple(column for column in table.columns if column.visible)
            parts.append('<table><thead><tr>')
            parts.extend(f"<th>{escape(column.title + (' (' + column.unit + ')' if column.unit else ''))}</th>" for column in columns)
            parts.append("</tr></thead><tbody>")
            for row in table.rows:
                if not row.include_in_publication:
                    continue
                parts.append("<tr>" + "".join(f"<td>{escape(row.cells[column.id].display) if column.id in row.cells else '—'}</td>"
                                               for column in columns) + "</tr>")
            parts.append("</tbody></table>")
            if table.method:
                parts.append(f'<p class="note">{escape(table.method)}</p>')
            for warning in table.warnings:
                parts.append(f'<p class="note">{escape(warning.message)}</p>')
    return "\n".join((*parts, "</body></html>"))
