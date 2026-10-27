#!/usr/bin/env python3
"""Generate an offline HTML report from saved OpenROAD toolkit runs."""

import argparse
import csv
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def esc(value):
    return html.escape(str(value if value not in (None, "") else "—"), quote=True)


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def read_manifest(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_history(path):
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream, delimiter="\t"))
    except (OSError, csv.Error):
        return []


def number(value):
    try:
        return float(str(value).strip().replace(",", "").split()[0])
    except (ValueError, TypeError, IndexError):
        return None


def timing_details(text):
    result = {}
    patterns = {
        "worst_slack_ns": r"worst slack\s+max\s+([-+]?\d+(?:\.\d+)?)",
        "wns_ns": r"wns\s+max\s+([-+]?\d+(?:\.\d+)?)",
        "tns_ns": r"tns\s+max\s+([-+]?\d+(?:\.\d+)?)",
        "min_period_ns": r"period_min\s*=\s*([-+]?\d+(?:\.\d+)?)",
        "fmax_mhz": r"fmax\s*=\s*([-+]?\d+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result[key] = match.group(1)
    return result


def link_for(run_dir, relative, label):
    target = run_dir / relative
    if not target.is_file():
        return ""
    href = Path("runs") / run_dir.name / relative
    return f'<a href="{esc(href.as_posix())}">{esc(label)}</a>'




def _generate_svg_chart(title, x_label, y_label, points, zero_line=False):
    """Renders an offline, standalone SVG scatter/line chart."""
    valid_pts = []
    for x, y, lbl in points:
        try:
            if x is not None and y is not None:
                valid_pts.append((float(x), float(y), str(lbl)))
        except (ValueError, TypeError):
            continue

    if len(valid_pts) < 2:
        return f"""
        <div class="chart-box">
            <h3>{title}</h3>
            <p class="chart-empty">Insufficient numeric data (requires &ge; 2 runs).</p>
        </div>"""

    valid_pts.sort(key=lambda p: p[0])
    xs = [p[0] for p in valid_pts]
    ys = [p[1] for p in valid_pts]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if min_x == max_x:
        max_x += 1.0
    if min_y == max_y:
        max_y += 1.0
        min_y -= 0.5

    if zero_line:
        min_y = min(min_y, 0.0)
        max_y = max(max_y, 0.0)

    W, H = 340, 190
    pad_l, pad_r, pad_t, pad_b = 48, 16, 20, 36
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b

    def tx(x):
        return pad_l + ((x - min_x) / (max_x - min_x)) * plot_w

    def ty(y):
        return pad_t + plot_h - (((y - min_y) / (max_y - min_y)) * plot_h)

    svg = []
    svg.append(f'<rect width="{W}" height="{H}" fill="#ffffff" rx="4"/>')
    svg.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t + plot_h}" stroke="#cbd5e1" stroke-width="1"/>')
    svg.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{pad_l + plot_w}" y2="{pad_t + plot_h}" stroke="#cbd5e1" stroke-width="1"/>')

    if zero_line and min_y <= 0.0 <= max_y:
        y0 = ty(0.0)
        svg.append(f'<line x1="{pad_l}" y1="{y0}" x2="{pad_l + plot_w}" y2="{y0}" stroke="#ef4444" stroke-dasharray="3,3" stroke-width="1.2"/>')
        svg.append(f'<text x="{pad_l + plot_w - 4}" y="{y0 - 3}" font-size="9" fill="#ef4444" text-anchor="end">0.0 (slack)</text>')

    coords = [f"{tx(x):.1f},{ty(y):.1f}" for x, y, _ in valid_pts]
    svg.append(f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{" ".join(coords)}"/>')

    for x, y, lbl in valid_pts:
        svg.append(f'<circle cx="{tx(x):.1f}" cy="{ty(y):.1f}" r="3.5" fill="#1e40af" stroke="#ffffff" stroke-width="1"><title>{lbl}: ({x}, {y})</title></circle>')

    svg.append(f'<text x="{W//2}" y="{H - 6}" font-size="10" fill="#64748b" text-anchor="middle">{x_label}</text>')
    svg.append(f'<text transform="rotate(-90)" x="{- (pad_t + plot_h // 2)}" y="12" font-size="10" fill="#64748b" text-anchor="middle">{y_label}</text>')
    svg.append(f'<text x="{pad_l}" y="{pad_t + plot_h + 12}" font-size="9" fill="#94a3b8" text-anchor="middle">{min_x:.1f}</text>')
    svg.append(f'<text x="{pad_l + plot_w}" y="{pad_t + plot_h + 12}" font-size="9" fill="#94a3b8" text-anchor="middle">{max_x:.1f}</text>')

    return f"""
    <div class="chart-box">
        <h3>{title}</h3>
        <svg viewBox="0 0 {W} {H}" class="ppa-svg" xmlns="http://www.w3.org/2000/svg">
            {''.join(svg)}
        </svg>
    </div>"""

def generate_ppa_charts(rows):
    """Generates the container with all 3 PPA comparison charts."""
    slack_pts, area_pts, power_pts = [], [], []
    for r in rows:
        get_val = r.get if isinstance(r, dict) else lambda k: getattr(r, k, None)
        run_id = get_val("id") or get_val("run_id") or "run"
        clk_raw = get_val("clock") or get_val("clk_ns") or get_val("clock_period")
        try:
            clk = float(clk_raw) if clk_raw not in (None, "", "—") else None
        except (ValueError, TypeError):
            clk = None

        if clk is None:
            continue

        try:
            s = get_val("slack") or get_val("slack_ns")
            if s not in (None, "", "—"):
                slack_pts.append((clk, float(s), run_id))
        except (ValueError, TypeError):
            pass

        try:
            a = get_val("area") or get_val("area_um2")
            if a not in (None, "", "—"):
                area_pts.append((clk, float(a), run_id))
        except (ValueError, TypeError):
            pass

        try:
            p = get_val("power") or get_val("power_mW")
            if p not in (None, "", "—"):
                power_pts.append((clk, float(p), run_id))
        except (ValueError, TypeError):
            pass

    c1 = _generate_svg_chart("Timing Slack vs. Period", "Clock Period (ns)", "Slack (ns)", slack_pts, zero_line=True)
    c2 = _generate_svg_chart("Design Area vs. Period", "Clock Period (ns)", "Area (um²)", area_pts)
    c3 = _generate_svg_chart("Total Power vs. Period", "Clock Period (ns)", "Power (mW)", power_pts)

    return f"""
    <section class="charts-container">
        <h2 style="font-size: 1.15rem; margin-bottom: 0.75rem;">PPA Trade-Off Trends</h2>
        <div class="charts-grid">
            {c1}
            {c2}
            {c3}
        </div>
    </section>
    """

def main():
    parser = argparse.ArgumentParser(
        description="Generate an offline HTML report for a saved ORFS project."
    )
    parser.add_argument("project", help="Project directory")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: Project directory not found: {project}", file=sys.stderr)
        return 2

    out_dir = project / "out"
    runs_dir = out_dir / "runs"
    history = read_history(out_dir / "runs.tsv")

    # Use run history as the primary source, but include saved run directories
    # that may not yet appear in runs.tsv.
    by_id = {}
    for row in history:
        run_id = (row.get("id") or "").strip()
        if run_id and re.fullmatch(r"[A-Za-z0-9_.+-]+", run_id):
            by_id[run_id] = dict(row)

    if runs_dir.is_dir():
        for run_path in sorted(runs_dir.iterdir()):
            if run_path.is_dir():
                by_id.setdefault(run_path.name, {"id": run_path.name})

    rows = []
    for run_id, row in by_id.items():
        run_dir = runs_dir / run_id
        manifest = read_manifest(run_dir / "manifest.json")
        summary = read_text(run_dir / "summary.txt")
        timing = timing_details(read_text(run_dir / "reports" / "6_finish.rpt"))

        # Prefer run-history values, then manifest values, then timing reports.
        def get_value(key, *fallbacks):
            value = row.get(key)
            if value not in (None, ""):
                return value
            for fallback in fallbacks:
                value = manifest.get(fallback)
                if value not in (None, "", "unknown", "-"):
                    return value
            return "—"

        slack = get_value("slack_ns", "slack_ns")
        if slack == "—":
            slack = timing.get("worst_slack_ns", "—")

        drc = get_value("drc", "drc")
        if drc == "—":
            match = re.search(r"DRC\s*:\s*(\d+)\s+violations", summary, re.I)
            if match:
                drc = match.group(1)

        gds_exists = (run_dir / "6_final.gds").is_file()
        summary_exists = (run_dir / "summary.txt").is_file()
        status = "Saved artifacts" if (gds_exists or summary_exists) else "History only"

        slack_num = number(slack)
        drc_num = number(drc)
        timing_status = (
            "MET" if slack_num is not None and slack_num >= 0
            else "VIOLATED" if slack_num is not None
            else "UNKNOWN"
        )
        drc_status = (
            "Clean" if drc_num == 0
            else "Violations" if drc_num is not None
            else "Unknown"
        )

        links = [
            link_for(run_dir, "summary.txt", "Summary"),
            link_for(run_dir, "reports/6_finish.rpt", "Timing"),
            link_for(run_dir, "reports/synth_stat.txt", "Synthesis"),
            link_for(run_dir, "reports/5_route_drc.rpt", "Route DRC"),
            link_for(run_dir, "6_final.gds", "GDS"),
            link_for(run_dir, "6_final.def", "DEF"),
            link_for(run_dir, "6_final.odb", "ODB"),
        ]
        links = [item for item in links if item]

        rows.append({
            "id": run_id,
            "clock": get_value("clk_ns", "clk_ns"),
            "slack": slack,
            "power": get_value("power_mW", "power_mW"),
            "area": get_value("area_um2", "area_um2"),
            "util": get_value("util", "util"),
            "drc": drc,
            "clock_tree": get_value("clock_tree", "clock_tree"),
            "status": status,
            "timing_status": timing_status,
            "drc_status": drc_status,
            "manifest": manifest,
            "timing": timing,
            "links": links,
        })

    rows.sort(key=lambda item: item["id"], reverse=True)

    def metric(row, key):
        return number(row.get(key))

    best_slack = max(
        (metric(row, "slack") for row in rows if metric(row, "slack") is not None),
        default=None,
    )
    clean_runs = sum(row["drc_status"] == "Clean" for row in rows)
    timing_met = sum(row["timing_status"] == "MET" for row in rows)

    def card(label, value, detail=""):
        return (
            '<section class="card"><div class="muted">' + esc(label) +
            '</div><div class="value">' + esc(value) +
            '</div><div class="muted small">' + esc(detail) + "</div></section>"
        )

    cards = "".join([
        card("Saved runs", len(rows), "From run history and saved snapshots"),
        card("Best recorded slack", f"{best_slack:g} ns" if best_slack is not None else "—",
             "Higher is better"),
        card("Timing met", f"{timing_met} / {len(rows)}", "Based on recorded slack"),
        card("DRC-clean runs", f"{clean_runs} / {len(rows)}", "Only known zero counts"),
    ])

    table_rows = []
    for row in rows:
        slack_num = metric(row, "slack")
        slack_class = (
            "good" if slack_num is not None and slack_num >= 0
            else "bad" if slack_num is not None
            else ""
        )
        timing_class = (
            "good" if row["timing_status"] == "MET"
            else "bad" if row["timing_status"] == "VIOLATED"
            else ""
        )
        drc_num = metric(row, "drc")
        drc_class = (
            "good" if drc_num == 0
            else "bad" if drc_num is not None
            else ""
        )
        links = " · ".join(row["links"]) if row["links"] else "No saved artifact links"

        table_rows.append(
            "<tr>"
            f'<td class="mono">{esc(row["id"])}</td>'
            f'<td>{esc(row["clock"])}</td>'
            f'<td class="{slack_class}">{esc(row["slack"])}</td>'
                        f'<td class="{timing_class}">{esc(row["timing_status"])}</td>'
            f'<td>{esc(row["power"])}</td>'
            f'<td>{esc(row["area"])}</td>'
            f'<td>{esc(row["util"])}</td>'
            f'<td class="{drc_class}">{esc(row["drc"])}</td>'
            f'<td>{esc(row["clock_tree"])}</td>'
            f'<td>{esc(row["status"])}</td>'
            f'<td class="links">{links}</td>'
            "</tr>"
        )

    details = []
    for row in rows:
        manifest = row["manifest"]
        timing = row["timing"]
        detail_items = [
            ("Platform", manifest.get("platform")),
            ("Input hash", manifest.get("input_hash")),
            ("Environment hash", manifest.get("env_hash")),
            ("OpenROAD", manifest.get("openroad")),
            ("Yosys", manifest.get("yosys")),
            ("KLayout", manifest.get("klayout")),
            ("ORFS commit", manifest.get("orfs_commit")),
            ("Timing met flag", manifest.get("timing_met")),
            ("Worst slack", timing.get("worst_slack_ns")),
            ("WNS", timing.get("wns_ns")),
            ("TNS", timing.get("tns_ns")),
            ("Minimum period", timing.get("min_period_ns")),
            ("Fmax", timing.get("fmax_mhz")),
        ]
        body = "".join(
            "<tr><th>" + esc(label) + "</th><td>" + esc(value) + "</td></tr>"
            for label, value in detail_items if value not in (None, "")
        )
        details.append(
            f'<details><summary>{esc(row["id"])} — run details</summary>'
            f'<table class="details"><tbody>{body}</tbody></table></details>'
        )

    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    title = f"{project.name} — OpenROAD Run Report"
    script = r"""<script>
(() => {
  const table = document.getElementById("runsTable");
  const filter = document.getElementById("runFilter");
  if (!table) return;

  const body = table.tBodies[0];
  const headers = Array.from(table.tHead.rows[0].cells);
  let sortColumn = -1;
  let descending = false;

  filter?.addEventListener("input", () => {
    const query = filter.value.trim().toLowerCase();
    for (const row of body.rows) {
      row.hidden = !row.innerText.toLowerCase().includes(query);
    }
  });

  headers.forEach((header, column) => {
    if (!header.hasAttribute("data-sort")) return;
    header.tabIndex = 0;
    header.setAttribute("role", "button");
    header.setAttribute("aria-label", "Sort by " + header.innerText);

    const sort = () => {
      if (sortColumn === column) descending = !descending;
      else {
        sortColumn = column;
        descending = false;
      }

      const rows = Array.from(body.rows);
      rows.sort((a, b) => {
        const av = a.cells[column]?.innerText.trim() ?? "";
        const bv = b.cells[column]?.innerText.trim() ?? "";
        const an = Number(av.replace(/[%,$µ²a-zA-Z ]/g, ""));
        const bn = Number(bv.replace(/[%,$µ²a-zA-Z ]/g, ""));
        const numeric = av !== "" && bv !== "" &&
          Number.isFinite(an) && Number.isFinite(bn) &&
          /[-+]?\d/.test(av) && /[-+]?\d/.test(bv);
        const result = numeric
          ? an - bn
          : av.localeCompare(bv, undefined, {numeric: true, sensitivity: "base"});
        return descending ? -result : result;
      });
      rows.forEach(row => body.appendChild(row));
      headers.forEach((h, i) => {
        if (h.hasAttribute("data-sort")) {
          h.setAttribute("aria-sort",
            i !== sortColumn ? "none" : descending ? "descending" : "ascending");
        }
      });
    };

    header.addEventListener("click", sort);
    header.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        sort();
      }
    });
  });
})();
</script>"""

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ margin: 0 auto; padding: 24px; max-width: 1500px; line-height: 1.45; }}
h1 {{ margin-bottom: 4px; }}
.muted {{ opacity: .72; }}
.small {{ font-size: .86rem; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 12px; margin: 24px 0; }}
.card {{ border: 1px solid #8886; border-radius: 10px; padding: 16px; }}
.value {{ font-size: 1.65rem; font-weight: 650; margin: 8px 0; }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
th[data-sort] {{ cursor: pointer; user-select: none; }}
.controls {{ display:flex; gap:12px; flex-wrap:wrap; margin:12px 0; }}
.controls input {{ padding:9px; min-width:260px; max-width:100%; }}
th, td {{ padding: 10px; border-bottom: 1px solid #8885; text-align: left; vertical-align: top; }}
th {{ position: sticky; top: 0; background: Canvas; }}
.mono {{ font-family: ui-monospace, monospace; white-space: nowrap; }}
.good {{ color: #16803c; font-weight: 650; }}
.bad {{ color: #d33; font-weight: 650; }}
.links {{ min-width: 210px; }}
a {{ color: LinkText; }}
details {{ border: 1px solid #8885; border-radius: 8px; margin: 10px 0; padding: 12px; }}
summary {{ cursor: pointer; font-weight: 600; }}
.details {{ margin-top: 10px; }}
footer {{ margin-top: 28px; font-size: .85rem; opacity: .7; }}
@media print {{ body {{ max-width: none; }} th {{ position: static; }} }}

.charts-container {{ margin: 1.5rem 0; }}
.charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; }}
.chart-box {{ border: 1px solid #8886; border-radius: 8px; padding: 12px; }}
.chart-box h3 {{ font-size: 0.95rem; margin: 0 0 8px 0; }}
.chart-empty {{ font-size: 0.85rem; opacity: 0.7; font-style: italic; padding: 2rem 0; text-align: center; }}
.ppa-svg {{ width: 100%; height: auto; display: block; }}
</style>
</head>
<body>
<header>
<h1>{esc(title)}</h1>
<div class="muted">Project: {esc(project)} · Generated: {esc(generated)}</div>
<p>This report reads saved run data only. It does not launch or modify a design flow.
Metrics are shown only when recorded in run history, manifests, summaries, or timing reports.</p>
</header>
<div class="cards">{cards}</div>
<h2>Run history</h2>
<div class="controls">
<input id="runFilter" type="search" placeholder="Filter runs, metrics, or status..." aria-label="Filter run history">
<span class="muted small">Select a column heading to sort. Select it again to reverse.</span>
</div>
<div class="table-wrap">
{generate_ppa_charts(rows)}
<table id="runsTable">
<thead><tr>
<th data-sort>Run ID ↕</th><th data-sort>Clock (ns) ↕</th><th data-sort>Slack (ns) ↕</th><th data-sort>Timing ↕</th><th data-sort>Power (mW) ↕</th>
<th data-sort>Area (µm²) ↕</th><th data-sort>Utilization ↕</th><th data-sort>DRC ↕</th><th data-sort>Clock tree ↕</th>
<th data-sort>Saved data ↕</th><th>Artifacts</th>
</tr></thead>
<tbody>
{''.join(table_rows) if table_rows else '<tr><td colspan="11">No saved runs found.</td></tr>'}
</tbody>
</table>
</div>
<h2>Run details</h2>
{''.join(details) if details else '<p>No saved run details are available.</p>'}
<footer>Generated locally by Tools/oreport.py. All links are relative to this report.</footer>
{script}
</body>
</html>
"""

    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "report.html"
    output.write_text(document, encoding="utf-8")
    print(f"Report: {output}")
    print(f"Runs included: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
