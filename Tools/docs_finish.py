#!/usr/bin/env python3
"""Installs Docs/TOOLKIT-README.md (copy given as argument), appends the output-map / Yosys / GitHub sections from flow.json,
and writes README.md at the repo root. Backs up an existing Docs file first."""
import json, os, shutil, sys, time
from pathlib import Path

BASE = Path(os.environ.get("ORFS_ROOT") or (Path.home() / "Ammar_Linux" / "OpenROAD"))
FJ = BASE / "Tools" / "wizard" / "flow.json"
RD = BASE / "Docs" / "TOOLKIT-README.md"
stamp = time.strftime("%Y%m%d-%H%M%S")
if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
    sys.exit("usage: python3 -I docs_finish.py <downloaded TOOLKIT-README.md>")
RD.parent.mkdir(parents=True, exist_ok=True)
if RD.exists():
    shutil.copy2(RD, BASE / "Archive" / "encfix" / f"TOOLKIT-README.md.before-docsfinish.{stamp}")
shutil.copy2(sys.argv[1], RD)
# ---- docs: where every step writes its files
if RD.exists() and "## 9. Where each step" not in RD.read_text(encoding="utf-8"):
    steps = json.loads(FJ.read_text(encoding="utf-8"))["steps"]
    rows = []
    for s in steps:
        if s.get("type") != "flow":
            continue
        rows.append(f"| {s['title']} | `{s['cmd']}` | `results/{s['result']}` | "
                    + (", ".join(f"`logs/{x}`" for x in s.get("logs", [])) or "-") + " | "
                    + (", ".join(f"`reports/{x}`" for x in s.get("reports", [])) or "-") + " |")
    doc = f"""
## 9. Where each step writes its files

Every project folder has three shortcuts, `Projects/<name>/results`, `logs` and `reports`. They point to the real ORFS folders
`OpenROAD-flow-scripts/flow/{{results,logs,reports}}/<platform>/<design>/base/`. Paths below are relative to those shortcuts.

| Step | Command | Result | Logs | Reports |
|---|---|---|---|---|
""" + "\n".join(rows) + """

Other places:
- `Projects/<name>/make.log`: the full output of the last flow command (first thing to read after a failure).
- `Projects/<name>/out/runs/<id>/`: a saved copy of every finished run: `6_final.gds`, `6_final.v/.def/.spef/.odb`, `summary.txt`, `manifest.json`, `reports/`, `inputs/` (the RTL, SDC and config used), `3d/` (2.5D script).
- `Projects/<name>/out/runs.tsv`: the table behind `oruns`; `out/latest` points at the newest run.
- `Projects/<name>/sim/wave.vcd`: waveform from `osim`.
- `Projects/<name>/out/report.html`: the HTML report (section 10).
- In the wizard, `l` shows a step's log and `p` its report.

## 10. HTML report, Yosys and GitHub

- **HTML report:** `oreport <name>` writes `Projects/<name>/out/report.html` (runs, area, power, timing, charts, saved reports). In the wizard hub press `w`: it builds the report and opens it in the browser.
- **Yosys:** `oyosys [rtl|net] [name]` opens an interactive Yosys shell with the design loaded: `rtl` reads your Verilog, `net` reads the synthesized netlist with the platform library. In the wizard, at the Synthesis step press `y` (RTL) or `n` (netlist); in the hub `y`. Type `exit` to come back. Inside Yosys: `stat`, `ls`, `synth -top <top>`, `abc ...`, `show` (needs graphviz).
- **GitHub:** `opush "message"` commits everything whitelisted in `.gitignore` (Tools, Docs, each project's rtl/tb/SDC/config, saved runs' final GDS, summaries and reports, the HTML report) and pushes to `origin main`. Files over 5 MB stop the push. Use `oprune` to keep the number of saved runs small.
- **Hub marks:** step 10 shows a red cross when timing or DRC failed, and an amber warning when timing was not checked.
"""
    RD.write_text(RD.read_text(encoding="utf-8").rstrip("\n") + "\n" + doc, encoding="utf-8")
    print(f"docs updated: {RD}")
else:
    print("docs already contain section 9, nothing to add")

shutil.copy2(RD, BASE / "README.md")
print(f"README.md written: {BASE / 'README.md'}")
