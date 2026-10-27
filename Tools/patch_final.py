#!/usr/bin/env python3
"""Patch 6: hub shows a red cross when the GDSII timing/DRC failed (amber warning when timing was not checked),
Yosys shell from the wizard (y = RTL, n = synthesized netlist) and `oyosys`, HTML report key (w) in the hub,
`opush` (commit and push to GitHub), and a "where are the outputs" section in Docs/TOOLKIT-README.md.
Backs up first, aborts if an anchor is not found exactly once, rolls back by itself if a check fails."""
import json, os, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(os.environ.get("ORFS_ROOT") or (Path.home() / "Ammar_Linux" / "OpenROAD"))
SH = BASE / "Tools" / "orfs-tools.sh"
PY = BASE / "Tools" / "wizard" / "chipwiz.py"
FJ = BASE / "Tools" / "wizard" / "flow.json"
RD = BASE / "Docs" / "TOOLKIT-README.md"
BK = BASE / "Archive" / "encfix"
stamp = time.strftime("%Y%m%d-%H%M%S")

HELPERS = '''def verdict(ctx, st, status, mark, note):
    """GDSII step: a red cross when timing or DRC failed, an amber warning when timing was never checked."""
    if not st.get("summary") or status != "done":
        return mark, note
    try:
        import csv
        with open(ctx.proj / "out" / "runs.tsv", encoding="utf-8") as f:
            last = list(csv.reader(f, delimiter="\\t"))[-1]
        slack, drc = last[2], last[6]
    except Exception:
        return mark, note
    try:
        import math
        s = float(slack)
        if not math.isfinite(s):
            raise ValueError
    except ValueError:
        return amber("⚠"), f"timing not checked (slack {slack})"
    if s < 0:
        return rose("✗"), f"timing failed (slack {s:.2f} ns): raise the clock with c, then rebuild"
    if drc not in ("0", "?"):
        return rose("✗"), f"DRC failed ({drc} violations)"
    return mark, note

def run_yosys(ctx, mode):
    print(dim("  Opening the Yosys shell. Type help for commands, exit to come back here."))
    subprocess.call(["zsh", "-c", f"unalias -a 2>/dev/null; source {TOOLS_SH}; oyosys {mode} {ctx.name}"])

def open_report(ctx):
    rc, out, _ = spin("Building the HTML report", f"oreport {ctx.name}")
    print()
    for l in out.splitlines():
        if l.strip():
            print("  " + dim(l))
    rep = ctx.proj / "out" / "report.html"
    if rc == 0 and rep.exists():
        subprocess.Popen(["xdg-open", str(rep)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(green("  ✓ Report opened in your browser: ") + str(rep))
    else:
        print(rose("  ✗ Could not build the report. Run the GDSII step first so a run is saved."))

# ---------------- checks ----------------
'''

EDITS = [
 ("# ---------------- checks ----------------\n", HELPERS, "helpers"),
 ('        mark = {"done": green("✓"), "stale": amber("⚠"), "todo": dim("·")}[status]\n        title = st["title"]\n',
  '        mark = {"done": green("✓"), "stale": amber("⚠"), "todo": dim("·")}[status]\n        mark, note = verdict(ctx, st, status, mark, note)\n        title = st["title"]\n', "step menu mark"),
 ('            mark = {"done": green("✓"), "stale": amber("⚠"), "todo": dim("·")}[s]\n            print(f"   {i:>2}  {mark}  {st[\'title\']:<30} {dim(note)}")\n',
  '            mark = {"done": green("✓"), "stale": amber("⚠"), "todo": dim("·")}[s]\n            mark, note = verdict(ctx, st, s, mark, note)\n            print(f"   {i:>2}  {mark}  {st[\'title\']:<30} {dim(note)}")\n', "hub mark"),
 ('            kl = " · k KLayout · 3 2.5D view" if st.get("klayout") else ""\n',
  '            kl = " · k KLayout · 3 2.5D view" if st.get("klayout") else ""\n            kl += " · y Yosys shell · n netlist in Yosys" if st.get("id") == "synth" else ""\n', "step menu help"),
 ('            elif a == "3" and st.get("klayout"):\n                open_klayout(ctx, True)\n            elif a == "r":\n                if ask("This clears the results of this step',
  '            elif a == "3" and st.get("klayout"):\n                open_klayout(ctx, True)\n            elif a in ("y", "n") and st.get("id") == "synth":\n                run_yosys(ctx, "net" if a == "n" else "rtl")\n            elif a == "r":\n                if ask("This clears the results of this step', "step menu keys"),
 ('            keys += ["k KLayout", "3 KLayout 2.5D view"]\n        a = ask("Press " + ", ".join(keys) + " · Enter to continue", "").lower()\n        if a == "v" and st.get("views"):\n            view_gui(ctx, st)\n',
  '            keys += ["k KLayout", "3 KLayout 2.5D view"]\n        if st.get("id") == "synth":\n            keys += ["y Yosys shell", "n netlist in Yosys"]\n        a = ask("Press " + ", ".join(keys) + " · Enter to continue", "").lower()\n        if a == "v" and st.get("views"):\n            view_gui(ctx, st)\n        elif a in ("y", "n") and st.get("id") == "synth":\n            run_yosys(ctx, "net" if a == "n" else "rtl")\n', "guided keys"),
 ('        print(dim("   c = change clock period   h = run history   x = clean everything   q = quit"))\n',
  '        print(dim("   c = change clock period   h = run history   w = HTML report   y = Yosys shell   x = clean everything   q = quit"))\n', "hub help"),
 ('        elif sel == "k":\n            open_klayout(ctx, False)\n        elif sel == "3d":\n',
  '        elif sel == "w":\n            open_report(ctx)\n        elif sel == "y":\n            run_yosys(ctx, "rtl")\n        elif sel == "k":\n            open_klayout(ctx, False)\n        elif sel == "3d":\n', "hub keys"),
]

SH_NEW = r'''
oyosys() {   # oyosys [rtl|net] [proj] : interactive Yosys shell with the design already loaded (rtl = your Verilog, net = the synthesized netlist)
  local mode=rtl
  [[ "$1" == rtl || "$1" == net ]] && { mode="$1"; shift; }
  local p plat top f c net lib
  p="$(_oproj "$1")" || return 1
  plat="$(_ovar "$p" PLATFORM)"; top="$(_ovar "$p" DESIGN_NAME)"
  command -v yosys >/dev/null || { echo "yosys not found (load the OSS CAD Suite environment first)"; return 1; }
  mkdir -p "$p/yosys"; f="$p/yosys/start-$mode.ys"
  local -a rtl libs; rtl=("$p"/rtl/*.v(N) "$p"/rtl/*.sv(N))
  libs=("$ORFS_FLOW/platforms/$plat/lib/"*tt*.lib(N) "$ORFS_FLOW/platforms/$plat/lib/"*.lib(N)); lib="${libs[1]:-}"
  if [[ "$mode" == net ]]; then
    for c in 1_2_yosys.v 1_synth.v; do [[ -f "$p/results/$c" ]] && { net="$p/results/$c"; break; }; done
    [[ -n "$net" ]] || { echo "no synthesized netlist yet: run osyn first"; return 1; }
    { [[ -n "$lib" ]] && echo "read_liberty -overwrite -setattr liberty_cell -lib $lib"
      echo "read_verilog -sv $net"; echo "hierarchy -top $top"; echo "shell"; } > "$f"
  else
    { echo "read_verilog -sv ${rtl[*]}"; echo "hierarchy -check -top $top"; echo "proc"; echo "opt"; echo "shell"; } > "$f"
  fi
  echo "Yosys shell for $top ($mode). Script: $f"
  echo "  try:  stat   ls   select -list t:*   synth -top $top   abc -g AND,OR,XOR   write_verilog out.v   exit"
  command -v dot >/dev/null && echo "  schematic:  show -format svg   (graphviz found)" || echo "  schematic (show) needs graphviz, which is not installed"
  ( cd "$p" && yosys -s "$f" )
}
opush() {   # opush ["message"] : commit and push all OpenROAD work (sources, final GDS, reports) to GitHub
  local r="$ORFS_ROOT" big
  [[ -d "$r/.git" ]] || { echo "not a git repo yet: run git_setup.zsh first"; return 1; }
  git -C "$r" add -A || return 1
  if git -C "$r" diff --cached --quiet; then
    echo "nothing new to commit"
  else
    big="$(git -C "$r" diff --cached --name-only --diff-filter=AM -z | xargs -0 -I{} du -k "$r/{}" 2>/dev/null | awk '$1 > 5000')"
    [[ -n "$big" ]] && { echo "files over 5 MB are staged, stopping:"; echo "$big"; git -C "$r" reset -q; return 1; }
    git -C "$r" commit -q -m "${*:-update $(date '+%Y-%m-%d %H:%M')}" && echo "✓ committed"
  fi
  git -C "$r" push -u origin main 2>&1 | tail -3
}
'''


def once(t, o, l, f):
    n = t.count(o)
    if n != 1:
        print(f"ABORT: anchor '{l}' found {n} times in {f} (expected 1). Nothing was changed.")
        sys.exit(1)


py_t = PY.read_text(encoding="utf-8")
sh_t = SH.read_text(encoding="utf-8")
for o, n, l in EDITS:
    once(py_t, o, l, "chipwiz.py")
if "oyosys()" in sh_t or "opush()" in sh_t:
    print("ABORT: oyosys/opush already exist. Nothing was changed.")
    sys.exit(1)

BK.mkdir(parents=True, exist_ok=True)
b_py = BK / f"chipwiz.py.before-final.{stamp}"
b_sh = BK / f"orfs-tools.sh.before-final.{stamp}"
b_rd = BK / f"TOOLKIT-README.md.before-final.{stamp}"
shutil.copy2(PY, b_py)
shutil.copy2(SH, b_sh)
if RD.exists():
    shutil.copy2(RD, b_rd)
print(f"backups in {BK}")

for o, n, l in EDITS:
    py_t = py_t.replace(o, n)
PY.write_text(py_t, encoding="utf-8")
SH.write_text(sh_t.rstrip("\n") + "\n" + SH_NEW, encoding="utf-8")


def rollback(why):
    shutil.copy2(b_py, PY)
    shutil.copy2(b_sh, SH)
    if b_rd.exists():
        shutil.copy2(b_rd, RD)
    print(f"ROLLED BACK ({why}). All files restored.")
    sys.exit(1)


r = subprocess.run(["zsh", "-n", str(SH)], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr)
    rollback("zsh -n failed")
print("zsh -n: OK")
r = subprocess.run([sys.executable, "-m", "py_compile", str(PY)], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr)
    rollback("py_compile failed")
print("py_compile: OK")

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
elif not RD.exists():
    print("Docs/TOOLKIT-README.md not found: docs section skipped (install the README first, then re-run is not needed; ask for the text)")

env = "unalias -a 2>/dev/null; export ORFS_ROOT=" + str(BASE) + "; source " + str(SH) + ";"
r = subprocess.run(["zsh", "-c", env + " otest quick; whence -w oyosys opush"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("\n".join((r.stdout + r.stderr).rstrip("\n").splitlines()[-4:]))
print("\nRollback if needed:")
print(f"  cp -v {b_py} {PY}")
print(f"  cp -v {b_sh} {SH}")
if b_rd.exists():
    print(f"  cp -v {b_rd} {RD}")
