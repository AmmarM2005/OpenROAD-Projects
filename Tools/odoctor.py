#!/usr/bin/env python3
"""odoctor: read-only health check of the OpenROAD / ORFS toolkit. It changes nothing.

usage: odoctor [-q] [project ...]
  -q        quiet: print only warnings, failures and the summary
  project   check only these projects (tools, storage and platforms are always checked)
exit code: 1 if any check FAILED, otherwise 0
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

HOME = Path.home()
ROOT = Path(os.environ.get("ORFS_ROOT") or (HOME / "Ammar_Linux" / "OpenROAD"))
FLOW = Path(os.environ.get("ORFS_FLOW") or (ROOT / "OpenROAD-flow-scripts" / "flow"))
PROJECTS = Path(os.environ.get("ORFS_PROJECTS") or (ROOT / "Projects"))
TOOLS = Path(os.environ.get("ORFS_TOOLS") or (ROOT / "Tools"))
TMP = Path(os.environ.get("ORFS_TMP") or (ROOT / "Tmp"))
OSS = Path(os.environ.get("ORFS_OSS") or (ROOT / "oss-cad-suite"))
YOSYS = Path(os.environ.get("ORFS_YOSYS") or (OSS / "bin" / "yosys"))
OPENROAD = os.environ.get("OPENROAD_EXE") or "/usr/bin/openroad"

TTY = sys.stdout.isatty()
def paint(code, s):
    return "\033[%sm%s\033[0m" % (code, s) if TTY else s
green = lambda s: paint("38;5;114", s)
amber = lambda s: paint("38;5;179", s)
rose = lambda s: paint("38;5;174", s)
dim = lambda s: paint("2", s)
bold = lambda s: paint("1", s)

RESULTS = []
ORDER = []
CUR = [""]

def section(title):
    CUR[0] = title
    if title not in ORDER:
        ORDER.append(title)

def _add(level, msg, fix=None):
    RESULTS.append((CUR[0], level, msg, fix))
def ok(msg): _add("ok", msg)
def info(msg): _add("info", msg)
def warn(msg, fix=None): _add("warn", msg, fix)
def fail(msg, fix=None): _add("fail", msg, fix)

def run(cmd, timeout=25):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as exc:
        return 127, str(exc)

def first_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""

def is_exe(path):
    return Path(str(path)).is_file() and os.access(str(path), os.X_OK)

def human(nbytes):
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return ("%d %s" % (size, unit)) if unit == "B" else ("%.1f %s" % (size, unit))
        size /= 1024
    return "%.1f TB" % size

def var(text, name):
    m = re.search(r"^export\s+%s\s*=\s*(\S+)" % re.escape(name), text, re.M)
    return m.group(1) if m else ""

# ------------------------------------------------------------------ tools
def check_tools():
    section("Tools")
    if is_exe(OPENROAD):
        rc, out = run([OPENROAD, "-version"])
        ok("openroad   %s   (%s)" % (first_line(out) or "version unknown", OPENROAD))
    else:
        fail("openroad not found at %s" % OPENROAD,
             "install the OpenROAD .deb (a copy may be in %s/Downloads)" % ROOT)
    if is_exe(YOSYS):
        rc, out = run([str(YOSYS), "-V"])
        m = re.search(r"Yosys\s+(\d+)\.(\d+)\S*", first_line(out))
        label = m.group(0) if m else (first_line(out)[:40] or "version unknown")
        if m and int(m.group(1)) == 0 and int(m.group(2)) < 30:
            fail("yosys   %s   is probably too old for the current ORFS scripts" % label,
                 "use the OSS CAD Suite build in %s, or set ORFS_OSS" % OSS)
        else:
            ok("yosys      %s   (%s)" % (label, YOSYS))
    else:
        fail("yosys not found at %s" % YOSYS,
             "unpack OSS CAD Suite to %s, or set ORFS_OSS to its folder" % OSS)
    for tool in ("iverilog", "vvp"):
        p = OSS / "bin" / tool
        found = str(p) if is_exe(p) else shutil.which(tool)
        if found:
            ok("%-10s %s" % (tool, found))
        else:
            warn("%s not found" % tool, "osim (simulation) needs it; it ships with OSS CAD Suite")
    kl = shutil.which("klayout")
    if kl:
        rc, out = run([kl, "-v"])
        ok("klayout    %s   (%s)" % (first_line(out) or "version unknown", kl))
    else:
        warn("klayout not found", "okl, o3d and oshow need it")
    v = sys.version_info
    if v >= (3, 8):
        ok("python     %d.%d.%d" % (v[0], v[1], v[2]))
    else:
        fail("python %d.%d is too old for the wizard" % (v[0], v[1]), "use Python 3.8 or newer")
    for tool, level in (("zsh", "fail"), ("make", "fail"), ("git", "warn")):
        p = shutil.which(tool)
        if p:
            ok("%-10s %s" % (tool, p))
        elif level == "fail":
            fail("%s not found" % tool, "the toolkit cannot run without it")
        else:
            warn("%s not found" % tool, "versions cannot be recorded in saved runs")
    if not shutil.which("xclip") and not shutil.which("wl-copy"):
        info("no xclip or wl-copy: the 2.5D script is saved to a file but not copied to the clipboard")

# ------------------------------------------------------------------ ORFS
def check_orfs():
    section("OpenROAD-flow-scripts")
    if not (FLOW / "Makefile").is_file():
        fail("flow folder not found: %s" % FLOW, "clone OpenROAD-flow-scripts under %s" % ROOT)
        return
    ok("flow folder   %s" % FLOW)
    rc, out = run(["git", "-C", str(FLOW), "rev-parse", "--short", "HEAD"])
    if rc == 0:
        ok("git commit    %s" % first_line(out))
    else:
        warn("the flow folder is not a git checkout", "saved runs cannot record the ORFS version")
    rc, out = run(["git", "-C", str(FLOW), "status", "--porcelain", "--untracked-files=no"])
    if rc == 0:
        lines = [l for l in out.splitlines() if l.strip()]
        if lines:
            names = ", ".join(l.split()[-1] for l in lines[:3])
            warn("%d tracked file(s) modified in the ORFS checkout (%s)" % (len(lines), names),
                 "intended? 'git -C %s diff --stat' shows the changes" % FLOW)
        else:
            ok("no local changes to tracked ORFS files")
    if not (FLOW.parent / "tools" / "install").is_dir():
        info("ORFS's own tools/install is not built (normal here: the toolkit uses Yosys from OSS CAD Suite)")
    if not is_exe(FLOW.parent / "tools" / "install" / "kepler-formal" / "bin" / "kepler-formal"):
        info("kepler-formal is not built: the logic equivalence check is off (LEC_CHECK=0 in every run)")

# ------------------------------------------------------------------ platforms
def check_platforms(used):
    section("Platforms")
    for p in sorted({"nangate45", "sky130hd"} | set(used)):
        d = FLOW / "platforms" / p
        problems = []
        if not d.is_dir():
            problems.append("folder missing")
        else:
            if not (d / "config.mk").is_file():
                problems.append("config.mk missing")
            if not any(d.glob("lib/*")):
                problems.append("no timing libraries in lib/")
            if not (any(d.glob("lef/*.lef")) or any(d.glob("lef/*.tlef"))):
                problems.append("no LEF files in lef/")
            if not any(d.glob("*.lyp")):
                problems.append("no .lyp layer file (KLayout colours and 2.5D layer numbers)")
        if problems:
            msg = "%s: %s" % (p, "; ".join(problems))
            fix = "compare with a fresh ORFS checkout: git -C %s status" % FLOW
            (fail if p in used else warn)(msg, fix)
        else:
            ok("%-10s config, libraries, LEF and layer files present" % p)

# ------------------------------------------------------------------ storage
def check_storage():
    section("Storage")
    for mount, warn_gb, fail_gb in (("/", 5, 2), ("/home", 20, 5)):
        if not os.path.exists(mount):
            continue
        du = shutil.disk_usage(mount)
        free = du.free / 1024.0 ** 3
        msg = "%-6s %.1f GB free of %.0f GB (%d%% used)" % (mount, free, du.total / 1024.0 ** 3,
                                                          round(100.0 * du.used / du.total))
        if free < fail_gb:
            fail(msg, "free space first: oclean / oprune on old projects, delete old downloads")
        elif free < warn_gb:
            warn(msg, "getting low: oprune old runs, delete downloads you no longer need")
        else:
            ok(msg)
    try:
        root_dev = os.stat("/").st_dev
        for label, path in (("ORFS flow folder", FLOW), ("projects", PROJECTS), ("temp folder", TMP)):
            if not path.exists():
                continue
            if os.stat(str(path)).st_dev == root_dev:
                warn("%s is on the same partition as / (%s)" % (label, path),
                     "move it under /home; the root partition is small here")
            else:
                ok("%s is not on the root partition" % label)
    except OSError:
        pass
    for label, path in (("flow/results", FLOW / "results"), ("Projects", PROJECTS), ("Tmp", TMP)):
        if not path.exists():
            continue
        rc, out = run(["du", "-sk", str(path)], timeout=90)
        try:
            kb = int(out.split()[0])
        except (ValueError, IndexError):
            continue
        if label == "Tmp" and kb > 1024 * 1024:
            warn("Tmp holds %s" % human(kb * 1024), "safe to empty when no flow is running: rm -rf %s/*" % TMP)
        else:
            info("%-13s %s" % (label, human(kb * 1024)))

# ------------------------------------------------------------------ display
def check_display():
    section("Display and GUI")
    if os.environ.get("DISPLAY"):
        ok("DISPLAY=%s" % os.environ["DISPLAY"])
    else:
        warn("DISPLAY is not set", "run the GUI commands from a terminal inside the desktop session")
    session = os.environ.get("XDG_SESSION_TYPE", "")
    if session:
        info("session type: %s" % session)
    try:
        text = (TOOLS / "orfs-tools.sh").read_text()
    except OSError:
        text = ""
    if "QT_QPA_PLATFORM=xcb" in text:
        ok("toolkit forces Qt apps onto X11 (QT_QPA_PLATFORM=xcb)")
    else:
        warn("toolkit does not set QT_QPA_PLATFORM=xcb", "GUIs may fail to open under Wayland")
    if shutil.which("glxinfo"):
        rc, out = run(["glxinfo", "-B"])
        low = out.lower()
        if "direct rendering: yes" in low and "llvmpipe" not in low:
            m = re.search(r"OpenGL renderer string:\s*(.+)", out)
            ok("OpenGL: %s" % (m.group(1).strip() if m else "hardware accelerated"))
        elif "llvmpipe" in low:
            warn("OpenGL is using software rendering (llvmpipe)", "GUIs will be slow; check the graphics driver")
        else:
            warn("OpenGL direct rendering is not available", "check: glxinfo -B")
    else:
        info("glxinfo not installed, OpenGL not checked")

# ------------------------------------------------------------------ toolkit
def check_toolkit():
    section("Toolkit")
    files = [TOOLS / "orfs-tools.sh", TOOLS / "wizard" / "chipwiz.py", TOOLS / "wizard" / "flow.json",
             TOOLS / "25d" / "gen25d.py", TOOLS / "25d" / "frontend.json"]
    missing = [f for f in files if not f.is_file()]
    if missing:
        for f in missing:
            fail("missing %s" % f, "restore it from %s/Archive" % ROOT)
        return
    ok("all toolkit files present")
    rc, out = run(["zsh", "-n", str(TOOLS / "orfs-tools.sh")])
    if rc == 0:
        ok("orfs-tools.sh parses")
    else:
        fail("orfs-tools.sh has a syntax error: %s" % first_line(out), "roll back: see the newest Archive/v3*-backup/rollback.sh")
    for f in (TOOLS / "wizard" / "chipwiz.py", TOOLS / "25d" / "gen25d.py", TOOLS / "odoctor.py"):
        if not f.is_file():
            continue
        try:
            compile(f.read_text(), str(f), "exec")
            ok("%s compiles" % f.name)
        except SyntaxError as exc:
            fail("%s: syntax error, line %s" % (f.name, exc.lineno), "roll back: see Archive/v3*-backup/rollback.sh")
    for f in (TOOLS / "wizard" / "flow.json", TOOLS / "25d" / "frontend.json"):
        try:
            json.loads(f.read_text())
            ok("%s is valid JSON" % f.name)
        except ValueError as exc:
            fail("%s is not valid JSON: %s" % (f.name, exc), "restore it from %s/Archive" % ROOT)
    try:
        zrc = (HOME / ".zshrc").read_text()
    except OSError:
        zrc = ""
    if "OpenROAD/Tools/orfs-tools.sh" in zrc:
        ok("~/.zshrc loads the toolkit")
    else:
        warn("~/.zshrc does not load the toolkit", "add: source ~/Ammar_Linux/OpenROAD/Tools/orfs-tools.sh")
    names = ["_omake_v32", "_osnap_v32", "ostale", "otest", "odoctor"]
    expr = " ".join("$+functions[%s]" % n for n in names)
    rc, out = run(["zsh", "-c", "source %s; print %s" % (TOOLS / "orfs-tools.sh", expr)])
    flags = out.split()
    if len(flags) == len(names):
        lost = [n for n, f in zip(names, flags) if f != "1"]
        if lost:
            warn("toolkit functions not defined: %s" % ", ".join(lost), "re-run the matching install-v3x.sh")
        else:
            ok("reliability and doctor functions are defined")
    else:
        warn("could not check the toolkit functions", "run: zsh -c 'source %s'" % (TOOLS / "orfs-tools.sh"))

# ------------------------------------------------------------------ projects
def check_projects(only):
    section("Projects")
    if not PROJECTS.is_dir():
        fail("Projects folder not found: %s" % PROJECTS, "create it, or set ORFS_ROOT")
        return set()
    dirs = sorted(p for p in PROJECTS.iterdir() if p.is_dir() and (p / "config.mk").is_file())
    if only:
        dirs = [p for p in dirs if p.name in only]
        for n in only:
            if not (PROJECTS / n / "config.mk").is_file():
                fail("no project called %s" % n, "list them with: ols")
    if not dirs:
        info("no projects found")
    used, seen = set(), {}
    for p in dirs:
        cfg = (p / "config.mk").read_text()
        name, plat = var(cfg, "DESIGN_NAME"), var(cfg, "PLATFORM")
        if plat:
            used.add(plat)
        seen.setdefault((plat, name), []).append(p.name)
        fails, warns = [], []
        if not name or not plat:
            fails.append("config.mk lacks DESIGN_NAME or PLATFORM")
        elif not (FLOW / "platforms" / plat).is_dir():
            fails.append("platform %s does not exist in ORFS" % plat)
        if "VERILOG_FILES" not in cfg or "SDC_FILE" not in cfg:
            fails.append("config.mk lacks VERILOG_FILES or SDC_FILE")
        rtl = sorted(list((p / "rtl").glob("*.v")) + list((p / "rtl").glob("*.sv")))
        if not rtl:
            fails.append("no RTL files in rtl/")
        else:
            text = "\n".join(f.read_text(errors="ignore") for f in rtl)
            if name and not re.search(r"\bmodule\s+%s\b" % re.escape(name), text):
                fails.append("no 'module %s' found in rtl/ (DESIGN_NAME must match the top module)" % name)
            if not re.search(r"\bclk\b", text):
                warns.append("no 'clk' signal in the RTL, but the SDC constrains a port called clk")
        sdc = p / "constraint.sdc"
        if not sdc.is_file():
            fails.append("constraint.sdc missing")
        else:
            s = sdc.read_text()
            if "create_clock" not in s:
                fails.append("constraint.sdc has no create_clock")
            if not re.search(r"^set clk_period", s, re.M):
                warns.append("constraint.sdc has no 'set clk_period' line (operiod and osweep need it)")
        if not list((p / "tb").glob("*.v")) and not list((p / "tb").glob("*.sv")):
            warns.append("no testbench in tb/ (osim has nothing to run)")
        m = re.search(r"^PROJ_DIR\s*=\s*(.+)$", cfg, re.M)
        if m and m.group(1).strip() != str(p):
            info("%s: PROJ_DIR points to %s (the toolkit corrects it on the next use)" % (p.name, m.group(1).strip()))
        runs = 0
        tsv = p / "out" / "runs.tsv"
        if tsv.is_file():
            rows = [l.split("\t") for l in tsv.read_text().splitlines()[1:] if l.strip()]
            runs = len(rows)
            if rows and len(rows[-1]) > 2:
                try:
                    if float(rows[-1][2]) < 0:
                        warns.append("the newest saved run misses timing (slack %s ns at %s ns)" % (rows[-1][2], rows[-1][1]))
                except ValueError:
                    pass
        label = "%s (%s)" % (p.name, plat or "?")
        if fails:
            fail("%s: %s" % (label, "; ".join(fails)), "fix it in %s, then run: ofresh %s" % (p, p.name))
        if warns:
            warn("%s: %s" % (label, "; ".join(warns)), "see the wizard hub for details: Chip Designing OPENROAD")
        if not fails and not warns:
            ok("%s: inputs consistent, %d saved run(s)" % (label, runs))
    for (plat, name), owners in seen.items():
        if len(owners) > 1:
            warn("projects %s share the same design name %s on %s" % (", ".join(owners), name, plat),
                 "they would overwrite each other's results in flow/results; rename one DESIGN_NAME")
    return used

# ------------------------------------------------------------------ output
def render(quiet):
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for sec, level, msg, fix in RESULTS:
        if level in counts:
            counts[level] += 1
    for sec in ORDER:
        items = [r for r in RESULTS if r[0] == sec]
        if quiet:
            items = [r for r in items if r[1] in ("warn", "fail")]
        if not items:
            continue
        print("\n" + bold(sec))
        for _, level, msg, fix in items:
            mark = {"ok": green("✓"), "warn": amber("⚠"), "fail": rose("✗"), "info": dim("·")}[level]
            text = msg if level != "info" else dim(msg)
            print("  %s %s" % (mark, text))
            if fix and level in ("warn", "fail"):
                print(dim("      → " + fix))
    print("\n  %s passed · %s warnings · %s failures" % (counts["ok"], counts["warn"], counts["fail"]))
    if counts["fail"]:
        print(rose("  ✗ fix the failures above first"))
    elif counts["warn"]:
        print(amber("  ✓ usable; the warnings are worth a look"))
    else:
        print(green("  ✓ everything looks healthy"))
    return counts["fail"]

def main():
    args = sys.argv[1:]
    quiet = any(a in ("-q", "--quiet") for a in args)
    names = [a for a in args if not a.startswith("-")]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return 0
    check_tools()
    check_orfs()
    used = check_projects(names)
    check_platforms(used)
    check_storage()
    check_display()
    check_toolkit()
    ORDER[:] = ["Tools", "OpenROAD-flow-scripts", "Platforms", "Storage", "Display and GUI", "Toolkit", "Projects"]
    return 1 if render(quiet) else 0

if __name__ == "__main__":
    sys.exit(main())
