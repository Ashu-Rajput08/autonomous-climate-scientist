"""Create self-contained Word exports with answer text, scientific notes, and chart images."""
from __future__ import annotations

from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _plot_png(figure) -> bytes:
    """Render the common Plotly chart types used by this app with Matplotlib."""
    payload = figure.to_dict()
    layout = payload.get("layout", {})
    fig, ax = plt.subplots(figsize=(8.0, 4.1), constrained_layout=True)
    fig.patch.set_facecolor("#10141c")
    ax.set_facecolor("#151d29")
    colors = ["#57c7b5", "#8c7cf0", "#ffad66", "#76a8ff", "#ec7691", "#e0ce65"]
    box_groups: dict[str, list] = {}
    plotted = False
    for index, trace in enumerate(payload.get("data", [])):
        kind = trace.get("type", "scatter")
        color = colors[index % len(colors)]
        label = str(trace.get("name", "Series"))
        if kind == "scattergeo":
            continue
        if kind == "box":
            values = trace.get("y") or trace.get("x") or []
            categories = trace.get("x") if trace.get("y") is not None else None
            if categories and len(categories) == len(values):
                for category, value in zip(categories, values):
                    box_groups.setdefault(str(category), []).append(value)
            else:
                box_groups.setdefault(label, []).extend(values)
            continue
        if kind == "bar":
            xs, ys = trace.get("x", []), trace.get("y", [])
            width = .78 / max(1, len(payload.get("data", [])))
            positions = list(range(len(xs)))
            offset = (index - (len(payload.get("data", [])) - 1) / 2) * width
            error = trace.get("error_y", {}).get("array")
            ax.bar([p + offset for p in positions], ys, width=width, label=label,
                   color=color, alpha=.9, yerr=error, capsize=2)
            ax.set_xticks(positions, [str(x) for x in xs], rotation=25, ha="right")
            plotted = True
            continue
        if kind == "histogram":
            values = trace.get("x", [])
            if values:
                ax.hist(values, bins=40, color=color, alpha=.76, label=label)
                plotted = True
            continue
        if kind == "scatter":
            xs, ys = trace.get("x", []), trace.get("y", [])
            if not xs or not ys:
                continue
            mode = trace.get("mode", "lines")
            if "lines" in mode:
                ax.plot(xs, ys, color=color, label=label, linewidth=1.7)
            if "markers" in mode or "lines" not in mode:
                ax.scatter(xs, ys, color=color, label=label, s=13, alpha=.72)
            plotted = True
    if box_groups:
        labels = list(box_groups)
        ax.boxplot([box_groups[key] for key in labels], labels=labels,
                   patch_artist=True, boxprops={"facecolor": "#267f78", "alpha": .8},
                   medianprops={"color": "#ffd28a", "linewidth": 1.5},
                   flierprops={"marker": ".", "markersize": 2, "alpha": .25})
        ax.tick_params(axis="x", labelrotation=25)
        plotted = True
    title = layout.get("title", "")
    if isinstance(title, dict):
        title = title.get("text", "")
    ax.set_title(str(title), color="#e8edf5", fontsize=11, pad=10)
    x_title = layout.get("xaxis", {}).get("title", {})
    y_title = layout.get("yaxis", {}).get("title", {})
    ax.set_xlabel(x_title.get("text", ""), color="#d2d9e4")
    ax.set_ylabel(y_title.get("text", ""), color="#d2d9e4")
    ax.tick_params(colors="#d2d9e4", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#64748b")
    if any(trace.get("name") for trace in payload.get("data", [])) and plotted:
        ax.legend(fontsize=7, facecolor="#1a2230", edgecolor="#475569", labelcolor="#e8edf5")
    if not plotted:
        ax.text(.5, .5, "Chart could not be rendered for this Word export",
                ha="center", va="center", color="#e8edf5", transform=ax.transAxes)
        ax.set_axis_off()
    output = BytesIO()
    fig.savefig(output, format="png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output.getvalue()


def _text_paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    safe = escape(text)
    return f'<w:p>{style_xml}<w:r><w:t xml:space="preserve">{safe}</w:t></w:r></w:p>'


def _markdown_blocks(text: str) -> list[str]:
    blocks = []
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if not stripped:
            continue
        if in_code:
            blocks.append(_text_paragraph(stripped, "Code"))
        elif stripped.startswith("### "):
            blocks.append(_text_paragraph(stripped[4:], "Heading2"))
        elif stripped.startswith("## "):
            blocks.append(_text_paragraph(stripped[3:], "Heading1"))
        elif stripped.startswith("# "):
            blocks.append(_text_paragraph(stripped[2:], "Title"))
        elif stripped.startswith("- "):
            blocks.append(_text_paragraph("•  " + stripped[2:]))
        elif stripped.startswith("|"):
            blocks.append(_text_paragraph(stripped.replace("|", "   │   "), "Code"))
        else:
            blocks.append(_text_paragraph(re.sub(r"[`*_]", "", stripped)))
    return blocks


def _image_paragraph(rel_id: str, image_id: int, title: str) -> str:
    cx, cy = 5_850_000, 2_980_000
    return (
        _text_paragraph(title, "Heading2") +
        f'<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{image_id}" name="Climate chart {image_id}"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="chart.png"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    )


def build_word_report(question: str, answer: str, metadata: dict) -> bytes:
    """Build a standalone .docx containing answer, methods, limitations, charts, and source report."""
    analysis = metadata.get("analysis", {})
    plan = analysis.get("experiment", {})
    results = analysis.get("results", {})
    quality = metadata.get("quality", {})
    issues = metadata.get("critic", {}).get("issues", [])
    body = [_text_paragraph("Climate research report", "Title"),
            _text_paragraph("Research question", "Heading1"),
            _text_paragraph(question),
            _text_paragraph("Answer", "Heading1"), *_markdown_blocks(answer),
            _text_paragraph("Analysis and rationale", "Heading1"),
            _text_paragraph("The selected dataset, analysis period, and methods below match the question and the available fields. These are the documented analysis choices and scientific caveats, not hidden chain-of-thought.")]
    details = [
        f"Dataset: {plan.get('dataset_id', 'not recorded')} · {plan.get('dataset', '')}",
        f"Objective: {plan.get('objective', 'not recorded')}",
        f"Variables: {', '.join(plan.get('variables', [])) or 'not recorded'}",
        f"Period: {quality.get('analysis_start', 'not recorded')} to {quality.get('analysis_end', 'not recorded')}",
        f"Question-requested timeline: {plan.get('time_range', {}).get('label', 'not narrowed in the question') if isinstance(plan.get('time_range'), dict) else plan.get('time_range', 'not narrowed in the question')}",
        f"Geographic scope: {', '.join(plan.get('locations', [])) or ('all available cities' if plan.get('all_cities') else 'single-site source or not specified')}",
        f"Resolution: {plan.get('temporal_resolution', 'daily')} · time semantics: {plan.get('timezone', 'source date labels')}",
        f"Methods: {', '.join(plan.get('methods', [])) or 'not recorded'}",
    ]
    body.extend(_text_paragraph(detail) for detail in details)
    body.append(_text_paragraph("Key results (structured values)", "Heading2"))
    body.extend(_markdown_blocks("```json\n" + json.dumps(results, indent=2, ensure_ascii=False, default=str) + "\n```"))
    body.append(_text_paragraph("Scientific notes and limitations", "Heading1"))
    body.extend(_text_paragraph(f"•  {item.get('severity', 'Note').title()}: {item.get('finding', '')}")
                for item in issues)
    if not issues:
        body.append(_text_paragraph("No critical data or method issue was flagged."))
    body.extend(_text_paragraph(f"•  {key.replace('_', ' ').title()}: {value:,}" if isinstance(value, int)
                                else f"•  {key.replace('_', ' ').title()}: {value}")
                for key, value in quality.items()
                if key in {"hourly_rows", "daily_rows", "duplicate_utc_timestamps", "invalid_utc_timestamps",
                           "non_hourly_intervals", "incomplete_ist_calendar_days"})

    image_entries = []
    try:
        from .data import load_experiment_dataset
        from .plotly_visualizations import build_charts, date_bounds
        dataset = load_experiment_dataset(plan.get("dataset_id", "open_meteo_single_location"))
        bounds = date_bounds(dataset, plan)
        figures = build_charts(dataset, dict(plan), bounds, None, None)
        for index, (chart_name, figure) in enumerate(figures, start=1):
            try:
                png = _plot_png(figure)
            except Exception:
                continue
            rel_id = f"rIdImage{index}"
            image_entries.append((f"word/media/chart{index}.png", png, rel_id))
            body.append(_image_paragraph(rel_id, index, chart_name))
    except Exception as exc:
        body.append(_text_paragraph(f"Charts were unavailable for export: {exc}"))

    report_path = metadata.get("report_path")
    if report_path and Path(report_path).is_file():
        body.append(_text_paragraph("Full scientific report", "Heading1"))
        body.extend(_markdown_blocks(Path(report_path).read_text(encoding="utf-8")))

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>'
        + "".join(body) + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="850" w:right="850" w:bottom="850" w:left="850"/></w:sectPr>'
        '</w:body></w:document>'
    )
    rels = ['<Relationship Id="rIdDoc" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>']
    rels.extend(f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{Path(name).name}"/>'
                for name, _, rel_id in image_entries)
    rel_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(rels) + '</Relationships>')
    doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{Path(name).name}"/>'
                          for name, _, rel_id in image_entries)
                + '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                + '</Relationships>')
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Default Extension="png" ContentType="image/png"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '</Types>')
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
        '<w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="21"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:spacing w:after="260"/></w:pPr><w:rPr><w:b/><w:color w:val="18324B"/><w:sz w:val="34"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="100"/><w:outlineLvl w:val="0"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="246B70"/><w:sz w:val="28"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
        '<w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="427D85"/><w:sz w:val="23"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/>'
        '<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="17"/></w:rPr></w:style>'
        '</w:styles>'
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", types)
        docx.writestr("_rels/.rels", rel_xml)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/_rels/document.xml.rels", doc_rels)
        docx.writestr("word/styles.xml", styles_xml)
        for name, png, _ in image_entries:
            docx.writestr(name, png)
    return output.getvalue()
