# author: yannik fontana, creation date: 08.05.2026
"""
Append an interactive Plotly measurement block to the daily lab-journal HTML file.

**Path:** ``<labjournalpath>/<YYYY>/<YYYYMMDD>.html`` (same tree as ``save_to_pptx``, ``.html`` only).

**Behaviour:** Each call appends one ``<section>`` (heading, tag, plots) and a TOC entry.
Empty ``figures`` → warning log and ``None`` (no file I/O).

**Dependencies:** ``plotly`` (``pip install plotly``). Plotly.js is loaded from CDN in the document.
After the **first** write that creates the daily ``.html`` file, opens it in **Microsoft Edge**
(64-bit Windows path below). Later appends that day do not launch the browser again.

Copy-to-clipboard uses the browser ``Clipboard`` API; Chromium/Edge tends to be most reliable.
"""
from __future__ import annotations

import datetime
import html
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

import plotly.io as pio
from plotly.graph_objects import Figure as GoFigure

from pyctrl.toolbox.software.save_to_pptx import _slide_title_line, _tag_text, labjournal_pptx_path

logger = logging.getLogger(__name__)

_MS_EDGE_64 = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

TOC_MARKER = "<!--PYCTRL_TOC_INSERT-->"
MAIN_MARKER = "<!--PYCTRL_MAIN_INSERT-->"

_CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, Segoe UI, sans-serif; background: #fafafa; }
.layout { display: flex; gap: 1.5rem; max-width: 1600px; margin: 0 auto; padding: 1rem; }
.toc-sidebar { flex: 0 0 260px; }
.toc-sticky { position: sticky; top: 0; align-self: flex-start; max-height: 100vh; overflow-y: auto; padding: 0.5rem 0.5rem 1rem 0; }
.toc-sticky h2 { margin: 0 0 0.75rem 0; font-size: 1rem; color: #333; }
#pyctrl-toc-list { list-style: none; padding: 0; margin: 0; }
#pyctrl-toc-list li { margin-bottom: 0.4rem; }
#pyctrl-toc-list a { text-decoration: none; color: #1565c0; word-break: break-word; font-size: 0.9rem; }
#pyctrl-toc-list a:hover { text-decoration: underline; }
.content { flex: 1; min-width: 0; background: #fff; padding: 1rem 1.25rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.measurement { margin-bottom: 2.5rem; padding-bottom: 2rem; border-bottom: 1px solid #e0e0e0; }
.measurement:last-child { border-bottom: none; }
.measurement h2 { margin: 0 0 0.5rem 0; font-size: 1.2rem; color: #222; }
.tag-block { white-space: pre-wrap; font-size: 0.9rem; color: #333; background: #f0f4f8; padding: 0.75rem 1rem; border-radius: 6px; margin: 0.75rem 0 1rem 0; border-left: 4px solid #1565c0; }
.plot-wrap { margin-top: 1.25rem; }
.plot-wrap button { margin-bottom: 0.5rem; cursor: pointer; padding: 0.4rem 0.85rem; font-size: 0.85rem; border: 1px solid #ccc; border-radius: 4px; background: #fff; }
.plot-wrap button:hover { background: #e3f2fd; border-color: #1565c0; }
"""

_JS = """
async function copyPlotToClipboard(divId) {
  const el = document.getElementById(divId);
  if (!el) {
    alert("Plot not found: " + divId);
    return;
  }
  try {
    const img = await Plotly.toImage(el, {format: "png", width: 1200, height: 800, scale: 1});
    const blob = await (await fetch(img)).blob();
    await navigator.clipboard.write([new ClipboardItem({"image/png": blob})]);
    alert("Copied to clipboard!");
  } catch (e) {
    console.error(e);
    alert("Copy failed (try Chrome; HTTPS or permission may be required): " + e);
  }
}
"""

_BLANK_DOC_FMT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Lab journal %s</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js" charset="utf-8"></script>
<style>
%s
</style>
<script>
%s
</script>
</head>
<body>
<div class="layout">
<aside class="toc-sidebar">
  <div class="toc-sticky">
    <h2>Measurements</h2>
    <ul id="pyctrl-toc-list">
%s
    </ul>
  </div>
</aside>
<main class="content">
<div id="pyctrl-sections">
%s
</div>
</main>
</div>
</body>
</html>
"""


def _new_document(title_date: str) -> str:
    return _BLANK_DOC_FMT % (
        html.escape(title_date),
        _CSS,
        _JS,
        TOC_MARKER,
        MAIN_MARKER,
    )


def labjournal_html_path(journal_date: datetime.date | None = None) -> Path:
    """``<labjournalpath>/<YYYY>/<YYYYMMDD>.html``."""
    return labjournal_pptx_path(journal_date).with_suffix(".html")


def _open_new_journal_in_edge(html_path: Path) -> None:
    """Open ``html_path`` in 64-bit Microsoft Edge (standard Windows install path)."""
    uri = html_path.resolve().as_uri()
    if not _MS_EDGE_64.is_file():
        logger.warning(
            "Microsoft Edge not found at %s; open the journal manually: %s",
            _MS_EDGE_64,
            html_path,
        )
        return
    try:
        subprocess.Popen([str(_MS_EDGE_64), uri], close_fds=True)
        logger.info("Opened new lab journal in Edge: %s", html_path)
    except OSError:
        logger.exception("Failed to launch Edge for %s", html_path)


def _anchor_base(filename: str) -> str:
    stem = Path(filename).stem if filename else "measurement"
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-")
    if not s:
        s = "measurement"
    if s[0].isdigit():
        s = "m-" + s
    return s


def _unique_section_id(existing_html: str, base: str) -> str:
    if f'id="{base}"' not in existing_html:
        return base
    n = 2
    while f'id="{base}-{n}"' in existing_html:
        n += 1
    return f"{base}-{n}"


def _build_section_html(
    *,
    section_id: str,
    title: str,
    tag_html: str,
    plot_fragments: list[tuple[str, str]],
) -> str:
    parts = [
        f'<section id="{html.escape(section_id, quote=True)}" class="measurement">',
        f"<h2>{html.escape(title)}</h2>",
    ]
    if tag_html.strip():
        parts.append(f'<div class="tag-block">{tag_html}</div>')
    for div_id, frag in plot_fragments:
        parts.append('<div class="plot-wrap">')
        parts.append(
            f'<button type="button" onclick="copyPlotToClipboard(\'{div_id}\')">'
            "Copy image to clipboard</button>"
        )
        parts.append(frag)
        parts.append("</div>")
    parts.append("</section>")
    return "\n".join(parts)


def save_to_html(
    data: Any,
    figures: Sequence[Any],
    *,
    journal_date: datetime.date | None = None,
    open_in_edge_on_create: bool = True,
) -> Path | None:
    """
    Append one measurement section (interactive Plotly figures) to today's journal HTML.

    When this call **creates** the daily ``.html`` file (first write of the day), opens it in
    Edge if ``open_in_edge_on_create`` is True. Subsequent appends the same day do not open
    a new browser window.

    Returns the journal file path, or ``None`` if ``figures`` is empty.
    """
    if not figures:
        logger.warning(
            "No figures provided to save_to_html; did not write anything to the lab journal HTML."
        )
        return None

    for i, fig in enumerate(figures):
        if not isinstance(fig, GoFigure):
            raise TypeError(
                f"figures[{i}] must be plotly.graph_objects.Figure, got {type(fig).__name__}"
            )

    path = labjournal_html_path(journal_date)
    title_date = path.stem
    is_creating_journal = not path.is_file()

    if path.is_file():
        doc = path.read_text(encoding="utf-8")
    else:
        doc = _new_document(title_date)

    if TOC_MARKER not in doc or MAIN_MARKER not in doc:
        raise ValueError(
            f"Lab journal HTML is missing pyctrl markers; refusing to patch: {path}"
        )

    filename = getattr(data, "filename", "") or ""
    base_anchor = _anchor_base(filename)
    section_id = _unique_section_id(doc, base_anchor)
    display_name = filename or section_id

    plot_bits: list[tuple[str, str]] = []
    for i, fig in enumerate(figures):
        div_id = f"{section_id}-plot-{i}"
        frag = pio.to_html(
            fig,
            include_plotlyjs=False,
            full_html=False,
            div_id=div_id,
            config={"displayModeBar": True},
        )
        plot_bits.append((div_id, frag))

    title = _slide_title_line(data)
    tag_plain = _tag_text(data)
    tag_html = html.escape(tag_plain, quote=False) if tag_plain else ""

    section_html = _build_section_html(
        section_id=section_id,
        title=title,
        tag_html=tag_html,
        plot_fragments=plot_bits,
    )

    toc_li = (
        f'<li><a href="#{html.escape(section_id, quote=True)}">'
        f"{html.escape(display_name)}</a></li>"
    )

    doc = doc.replace(TOC_MARKER, f"{toc_li}\n{TOC_MARKER}", 1)
    doc = doc.replace(MAIN_MARKER, f"{section_html}\n{MAIN_MARKER}", 1)

    path.write_text(doc, encoding="utf-8")
    logger.info(
        "Lab journal HTML updated: %s (section %s, %d plot(s))",
        path,
        section_id,
        len(figures),
    )
    if is_creating_journal and open_in_edge_on_create:
        _open_new_journal_in_edge(path)
    return path
