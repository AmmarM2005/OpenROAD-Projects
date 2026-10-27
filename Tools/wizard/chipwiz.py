#!/usr/bin/env python3
"""Chip Designing / OpenROAD wizard v2: guided walk-through plus a hub to jump to any step."""
import json, os, re, select, shutil, subprocess, sys, tempfile, textwrap, time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(os.environ.get("ORFS_ROOT", str(Path.home() / "Ammar_Linux" / "OpenROAD")))
OSS = Path(os.environ.get("ORFS_OSS", str(ROOT / "oss-cad-suite")))
WIZ = ROOT / "Tools" / "wizard"
PROJECTS = ROOT / "Projects"
TOOLS_SH = ROOT / "Tools" / "orfs-tools.sh"
FLOW = ROOT / "OpenROAD-flow-scripts" / "flow"
IVERILOG = OSS / "bin" / "iverilog"

TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if TTY else s
teal = lambda s: _c("38;5;80", s)
lav = lambda s: _c("38;5;147", s)
green = lambda s: _c("38;5;114", s)
amber = lambda s: _c("38;5;179", s)
rose = lambda s: _c("38;5;174", s)
dim = lambda s: _c("2", s)
bold = lambda s: _c("1", s)

class GoMenu(Exception): pass
class GoBack(Exception): pass
class GoStep(Exception):
    def __init__(self, n):
        super().__init__(n)
        self.n = n

def bye(msg=None):
    print(dim(msg or "\n  Paused. Run `Chip Designing OPENROAD` any time and give the same project name to come back.\n"))
    sys.exit(0)

def ask(prompt, default="", nav=True):
    try:
        s = input(f"  {lav('›')} {prompt}" + (dim(f" [{default}]") if default else "") + " ").strip()
    except (EOFError, KeyboardInterrupt):
        print(); bye()
    s = s or default
    if nav:
        low = s.lower()
        if low in ("q", "quit"): bye()
        if low in ("m", "menu"): raise GoMenu()
        if low in ("b", "back"): raise GoBack()
        mm = re.fullmatch(r"g\s*(\d+)", low)
        if mm: raise GoStep(int(mm.group(1)))
    return s

def box(title, lines, color=teal):
    wrapped = []
    for l in lines:
        wrapped += textwrap.wrap(l, 78) or [""]
    w = max([len(l) for l in wrapped] + [len(title) + 4, 50])
    print("\n" + color("╭─ " + title + " " + "─" * (w - len(title) - 1) + "╮"))
    for l in wrapped:
        print(color("│ ") + l + " " * (w - len(l)) + color(" │"))
    print(color("╰" + "─" * (w + 2) + "╯"))

def progress(i, n):
    filled = int(24 * (i - 1) / n)
    print(f"\n  {green('█' * filled)}{dim('░' * (24 - filled))}  {dim(f'step {i} of {n}')}")
    print(dim("  b back · m menu · g<N> go to step N · q pause"))

def spin(label, cmd):
    """Run a toolkit command in zsh with a spinner. Returns (returncode, output, seconds)."""
    full = f"source {TOOLS_SH}; {cmd}"
    tf = tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace")
    p = subprocess.Popen(["zsh", "-c", full], stdout=tf, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    t0, i = time.time(), 0
    try:
        while p.poll() is None:
            if TTY:
                sys.stdout.write(f"\r  {teal(frames[i % len(frames)])} {label}  {dim(str(int(time.time() - t0)) + 's')}   ")
                sys.stdout.flush()
            i += 1
            time.sleep(0.1)
    except KeyboardInterrupt:
        p.terminate(); print(); bye()
    if TTY:
        sys.stdout.write("\r" + " " * 70 + "\r")
    tf.seek(0)
    out = tf.read(); tf.close()
    return p.returncode, out, time.time() - t0

def pick_editor():
    env = os.environ.get("CHIPWIZ_EDITOR")
    if env and shutil.which(env.split()[0]):
        parts = env.split()
        return ("tty" if parts[0] in ("nano", "vim", "nvim", "vi", "emacs") else "gui"), parts
    if shutil.which("code"):
        return "gui", ["code", "--reuse-window"]
    for e in ("nvim", "nano", "vim"):
        if shutil.which(e):
            return "tty", [e]
    return None, None

def open_and_wait(path):
    kind, cmd = pick_editor()
    if kind == "tty":
        subprocess.run(cmd + [str(path)])
        return
    if kind == "gui":
        subprocess.Popen(cmd + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(dim("  Opened in your editor. Write your code, then save (Ctrl+S)."))
    else:
        print(dim(f"  No editor found. Open this file yourself:\n  {path}"))
    last = path.stat().st_mtime
    print(dim("  Waiting for you... press Enter here when you are done."))
    try:
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.5)
            if r:
                sys.stdin.readline()
                return
            m = path.stat().st_mtime
            if m != last:
                last = m
                print(green(f"  ✓ saved at {time.strftime('%H:%M:%S')}") + dim("  (press Enter when you are done editing)"))
    except KeyboardInterrupt:
        print(); bye()

# ---------------- state of each step ----------------
def rdir(ctx, sub="results"):
    return FLOW / sub / ctx.plat / ctx.name / "base"

def stub_text(st, name):
    return ("\n".join(st["stub"]).replace("@NAME@", name) + "\n") if st.get("stub") else None

def src_mtime(ctx):
    files = [ctx.proj / "constraint.sdc", ctx.proj / "config.mk"]
    for pat in ("*.v", "*.sv"):
        files += list((ctx.proj / "rtl").glob(pat))
    return max((f.stat().st_mtime for f in files if f.exists()), default=0)

_STALE = {}

def refresh_stale(ctx):
    """Ask the toolkit which stage results were built from the current inputs (content hashes)."""
    d = {}
    try:
        r = subprocess.run(["zsh", "-c", f"source {TOOLS_SH}; ostale {ctx.name}"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2:
                d[parts[0]] = parts[1]
    except Exception:
        d = {}
    _STALE[ctx.name] = d
    return d

def stale_state(ctx):
    if ctx.name not in _STALE:
        refresh_stale(ctx)
    return _STALE[ctx.name]

def step_status(ctx, st):
    """returns (done|stale|todo, note)"""
    if st["type"] == "edit":
        p = ctx.proj / st["file"].replace("{name}", ctx.name)
        if not p.exists():
            return "todo", "file missing"
        s = stub_text(st, ctx.name)
        if s is not None and p.read_text(errors="replace") == s:
            return "todo", "still the starter text"
        return "done", p.name
    res = rdir(ctx) / st["result"]
    if not res.exists():
        return "todo", "not run"
    t = res.stat().st_mtime
    state = stale_state(ctx).get(st["result"])
    if state == "fresh":
        return "done", time.strftime("%H:%M", time.localtime(t))
    if state == "stale":
        return "stale", "inputs differ from the ones this was built from"
    if t < src_mtime(ctx):
        return "stale", "inputs changed since this ran"
    return "done", time.strftime("%H:%M", time.localtime(t))

def verdict(ctx, st, status, mark, note):
    """GDSII step: a red cross when timing or DRC failed, an amber warning when timing was never checked."""
    if not st.get("summary") or status != "done":
        return mark, note
    try:
        import csv
        with open(ctx.proj / "out" / "runs.tsv", encoding="utf-8") as f:
            last = list(csv.reader(f, delimiter="\t"))[-1]
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
def check(st, ctx, path):
    kind = st.get("check")
    text = path.read_text(errors="replace")
    if kind == "rtl":
        if not re.search(rf"\bmodule\s+{re.escape(ctx.name)}\b", text):
            print(rose(f"  ✗ I can't find 'module {ctx.name}'. The top module must have exactly that name."))
            return False
        if st.get("stub") and text == stub_text(st, ctx.name):
            print(amber("  ! The file still has only the starter text."))
            return False
        if not re.search(r"\bclk\b", text):
            print(amber("  ! No 'clk' found. The constraints expect a clock port named clk."))
        if IVERILOG.exists():
            files = sorted(str(f) for f in (ctx.proj / "rtl").iterdir() if f.suffix in (".v", ".sv"))
            r = subprocess.run([str(IVERILOG), "-g2012", "-t", "null", *files], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                print(rose("  ✗ Syntax problem:"))
                for l in (r.stderr or r.stdout).strip().splitlines()[:10]:
                    print("    " + dim(l))
                return False
        print(green("  ✓ RTL looks good"))
        return True
    if kind == "tb":
        if st.get("stub") and text == stub_text(st, ctx.name):
            print(amber("  ! Still the starter testbench, so nothing is being tested yet."))
            return True
        rc, out, _ = spin("Simulating", f"osim {ctx.name}")
        for l in [l for l in out.strip().splitlines() if l.strip()][-10:]:
            print("    " + dim(l))
        if re.search(r"\bFAIL", out):
            print(rose("  ✗ The testbench reports a failure."))
            return False
        if re.search(r"error|syntax|unable", out, re.I):
            print(rose("  ✗ The simulation hit an error."))
            return False
        if "PASS" in out:
            print(green("  ✓ Simulation: PASS"))
        else:
            print(amber("  ! No PASS or FAIL line was printed. Add $display(\"PASS\"); once your checks are in."))
        return True
    if kind == "sdc":
        if "create_clock" not in text:
            print(amber("  ! No create_clock found. The flow needs a clock constraint."))
        if not re.search(r"^set clk_period", text, re.M):
            print(amber("  ! No 'set clk_period' line. osweep and operiod need it."))
        print(green("  ✓ constraints ok"))
        return True
    if kind == "cfg":
        m = re.search(r"DESIGN_NAME\s*=\s*(\S+)", text)
        if not m or m.group(1) != ctx.name:
            print(rose(f"  ✗ DESIGN_NAME must be {ctx.name}."))
            return False
        print(green("  ✓ config.mk ok"))
        return True
    return True

def edit_loop(st, ctx, path):
    while True:
        open_and_wait(path)
        if check(st, ctx, path):
            return
        if ask("Enter edits again, c continues anyway", "", nav=False).lower() == "c":
            return

# ---------------- viewing helpers ----------------
def view_gui(ctx, st):
    views = st.get("views") or []
    if not views:
        print(dim("  nothing to view for this step")); return
    key = views[-1][0]
    if len(views) > 1:
        print()
        for k, (_, label) in enumerate(views, 1):
            print(f"   {k}. {label}")
        sel = ask("Which view? (number)", str(len(views)), nav=False)
        if sel.isdigit() and 1 <= int(sel) <= len(views):
            key = views[int(sel) - 1][0]
    print(dim("  Opening (building first if needed)... close the window to come back."))
    r = subprocess.run(["zsh", "-c", f"source {TOOLS_SH}; ogui {key} {ctx.name}"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and re.search(r"error|FAILED|\*\*\*", out, re.I):
        print(rose("  ✗ The viewer reported a problem:"))
        for l in [l for l in out.splitlines() if l.strip()][-8:]:
            print("    " + dim(l))

def show_files(ctx, names, kind):
    d = rdir(ctx, "logs" if kind == "log" else "reports")
    avail = [d / n for n in names if (d / n).exists()]
    if not avail:
        print(amber(f"  No {kind} yet. Run the step first.")); return
    f = avail[0]
    if len(avail) > 1:
        print()
        for k, a in enumerate(avail, 1):
            print(f"   {k}. {a.name}")
        sel = ask("Which one? (number)", "1", nav=False)
        if sel.isdigit() and 1 <= int(sel) <= len(avail):
            f = avail[int(sel) - 1]
    print(dim(f"  {f}   (q leaves the viewer)"))
    subprocess.run(["less", "-FRX", str(f)])

def open_klayout(ctx, d25):
    gds = rdir(ctx) / "6_final.gds"
    if not gds.exists():
        print(amber("  The GDSII is not built yet. Run the GDSII step first."))
        return
    if d25:
        rc, out, _ = spin("Reading layer thickness and metal info", f"o3dgen {ctx.name}")
        print()
        for l in out.splitlines():
            if l.strip():
                print("  " + dim(l))
        if rc != 0:
            print(rose("  ✗ Could not prepare the 2.5D stack (see the messages above)."))
            return
        cmd = f"o3d {ctx.name}"
    else:
        cmd = f"okl {ctx.name}"
    subprocess.Popen(["zsh", "-c", f"source {TOOLS_SH}; {cmd}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(green("  ✓ KLayout is opening in its own window."))
    if d25:
        print(dim(f"    The 2.5D window should open by itself. If not: Tools > 2.5d View > New 2.5d Script, paste {ctx.proj / '3d' / 'view25d.rb'}"))

def run_flow_cmd(ctx, st, nav):
    while True:
        rc, out, secs = spin(st["title"], f"{st['cmd']} {ctx.name}")
        if rc == 0:
            print(green(f"  ✓ {st['title']} finished in {int(secs)}s"))
            return True
        print(rose(f"  ✗ {st['title']} failed"))
        for l in [l for l in out.splitlines() if l.strip()][-10:]:
            print("    " + dim(l))
        if st.get("hint"):
            print(amber("  Hint: " + st["hint"]))
        print(dim(f"  Full log: {ctx.proj / 'make.log'}"))
        if ask("Enter retries, x gives up", "", nav=nav).lower() == "x":
            return False

def show_summary(ctx):
    rc, out, _ = spin("Collecting results", f"osum {ctx.name}")
    print()
    for l in out.splitlines():
        col = green if "✓" in l else (rose if "✗" in l else (amber if "⚠" in l else (lambda s: s)))
        print("  " + col(l))

# ---------------- guided steps ----------------
def edit_step(st, i, n, ctx):
    path = ctx.proj / st["file"].replace("{name}", ctx.name)
    progress(i, n)
    box(st["title"], st["intro"] + [""] + ["•  " + t.replace("{name}", ctx.name) for t in st.get("tips", [])])
    print(f"  {dim('file:')} {path}")
    status, _ = step_status(ctx, st)
    if status == "done":
        if ask("Enter keeps it as it is, e edits it", "").lower() != "e":
            check(st, ctx, path)
            return
    else:
        hint = "Enter opens your editor" + (", s skips this step" if st.get("skippable") else "")
        if ask(hint, "").lower() == "s" and st.get("skippable"):
            print(dim("  skipped")); return
    edit_loop(st, ctx, path)

def flow_step(st, i, n, ctx):
    progress(i, n)
    box(st["title"], st["about"])
    refresh_stale(ctx)
    status, note = step_status(ctx, st)
    if status == "done":
        print(green(f"  ✓ already built ({note}) and up to date"))
        while True:
            a = ask("Enter moves on, v views it, r rebuilds from scratch", "").lower()
            if a == "v":
                view_gui(ctx, st); continue
            if a == "r":
                status = "stale"; break
            return
    elif status == "stale":
        print(amber(f"  ⚠ {note}. I will rebuild from a clean slate."))
    if ask("Enter runs it, s skips", "").lower() == "s":
        print(dim("  skipped")); return
    if status == "stale":
        spin("Cleaning old results", f"oclean {ctx.name}")
    if not run_flow_cmd(ctx, st, nav=True):
        raise GoMenu()
    if st.get("summary"):
        show_summary(ctx)
    while st.get("views") or st.get("klayout"):
        keys = []
        if st.get("views"):
            keys.append("v OpenROAD GUI")
        if st.get("klayout"):
            keys += ["k KLayout", "3 KLayout 2.5D view"]
        if st.get("id") == "synth":
            keys += ["y Yosys shell", "n netlist in Yosys"]
        a = ask("Press " + ", ".join(keys) + " · Enter to continue", "").lower()
        if a == "v" and st.get("views"):
            view_gui(ctx, st)
        elif a in ("y", "n") and st.get("id") == "synth":
            run_yosys(ctx, "net" if a == "n" else "rtl")
        elif a == "k" and st.get("klayout"):
            open_klayout(ctx, False)
        elif a == "3" and st.get("klayout"):
            open_klayout(ctx, True)
        else:
            break

def guided(ctx, steps, i):
    n = len(steps)
    while i < n:
        st = steps[i]
        try:
            (edit_step if st["type"] == "edit" else flow_step)(st, i + 1, n, ctx)
            i += 1
        except GoBack:
            i = max(0, i - 1)
        except GoStep as g:
            i = min(max(g.n - 1, 0), n - 1)
        except GoMenu:
            return
    box("Flow complete", [f"Project: {ctx.proj}", "The hub below lets you revisit any step."], color=green)

# ---------------- hub ----------------
def step_menu(ctx, steps, idx):
    """Actions for one step. Returns idx if the user wants the guided walk from here."""
    st = steps[idx]
    while True:
        refresh_stale(ctx)
        status, note = step_status(ctx, st)
        mark = {"done": green("✓"), "stale": amber("⚠"), "todo": dim("·")}[status]
        mark, note = verdict(ctx, st, status, mark, note)
        title = st["title"]
        print(f"\n  {bold(f'Step {idx + 1}: {title}')}  {mark} {dim(note)}")
        if st["type"] == "edit":
            extra = " · t run the simulation" if st.get("check") == "tb" else ""
            print(dim(f"   e edit it{extra} · g guided walk from here · Enter back"))
        else:
            kl = " · k KLayout · 3 2.5D view" if st.get("klayout") else ""
            kl += " · y Yosys shell · n netlist in Yosys" if st.get("id") == "synth" else ""
            print(dim("   v view in GUI · l log · p report" + kl + " · r rebuild up to here · g guided walk from here · Enter back"))
        a = ask("Choose", "", nav=False).lower()
        if a == "":
            return None
        if a == "g":
            return idx
        if st["type"] == "edit":
            path = ctx.proj / st["file"].replace("{name}", ctx.name)
            if a == "e":
                edit_loop(st, ctx, path)
                if st.get("check") in ("sdc", "cfg"):
                    print(amber("  Changes to the constraints or config.mk need a fresh run: use r in the hub."))
            elif a == "t" and st.get("check") == "tb":
                check(st, ctx, path)
            else:
                print(rose(f"  ✗ '{a}' is not an option for this step. Choose one of the keys shown above, or press Enter to go back."))
        else:
            if a == "v":
                view_gui(ctx, st)
            elif a == "l":
                show_files(ctx, st.get("logs", []), "log")
            elif a == "p":
                show_files(ctx, st.get("reports", []), "report")
            elif a == "k" and st.get("klayout"):
                open_klayout(ctx, False)
            elif a == "3" and st.get("klayout"):
                open_klayout(ctx, True)
            elif a in ("y", "n") and st.get("id") == "synth":
                run_yosys(ctx, "net" if a == "n" else "rtl")
            elif a == "r":
                if ask("This clears the results of this step and every later one. Rebuild? (Y/n)", "y", nav=False).lower().startswith("n"):
                    continue
                spin("Cleaning", f"oclean {ctx.name}")
                if run_flow_cmd(ctx, st, nav=False) and st.get("summary"):
                    show_summary(ctx)
            else:
                print(rose(f"  ✗ '{a}' is not an option for this step. Choose one of the keys shown above, or press Enter to go back to the hub."))

def hub(ctx, steps):
    n = len(steps)
    while True:
        refresh_stale(ctx)
        print("\n  " + teal(bold(f"── {ctx.name} · {ctx.plat} " + "─" * 30)))
        statuses = []
        for i, st in enumerate(steps, 1):
            s, note = step_status(ctx, st)
            statuses.append(s)
            mark = {"done": green("✓"), "stale": amber("⚠"), "todo": dim("·")}[s]
            mark, note = verdict(ctx, st, s, mark, note)
            print(f"   {i:>2}  {mark}  {st['title']:<30} {dim(note)}")
        print(dim("\n   number = open that step   a = guided walk from the first unfinished step"))
        print(dim("   r = run all remaining   s = summary   f = final layout (OpenROAD)   k = KLayout   3d = 2.5D view"))
        print(dim("   c = change clock period   h = run history   w = HTML report   y = Yosys shell   x = clean everything   q = quit"))
        sel = ask("What next?", "", nav=False).lower()
        if sel in ("q", "quit"):
            bye(dim("\n  Bye. Run `Chip Designing OPENROAD` any time to come back.\n")); return
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < n:
                r = step_menu(ctx, steps, idx)
                if r is not None:
                    guided(ctx, steps, r)
            else:
                print(rose(f"  ✗ Pick a number from 1 to {n}."))
        elif sel == "a":
            todo = [k for k, s in enumerate(statuses) if s != "done"]
            if not todo:
                print(green("  ✓ Everything is built and up to date."))
            else:
                guided(ctx, steps, todo[0])
        elif sel == "r":
            flow_idx = [k for k, st in enumerate(steps) if st["type"] == "flow"]
            if all(statuses[k] == "done" for k in flow_idx):
                print(green("  ✓ Nothing to do, all stages are up to date."))
                continue
            fresh = all(statuses[k] == "todo" for k in flow_idx)
            rc, out, secs = spin("Running the whole flow", ("orun" if fresh else "ofresh") + f" {ctx.name}")
            lines = [l for l in out.splitlines() if l.strip()]
            if rc != 0 or any("FAILED" in l for l in lines):
                print(rose("  ✗ The run failed:"))
                for l in lines[-10:]:
                    print("    " + dim(l))
                print(dim(f"  Full log: {ctx.proj / 'make.log'}"))
            else:
                print(green(f"  ✓ finished in {int(secs)}s"))
                show_summary(ctx)
        elif sel == "s":
            show_summary(ctx)
        elif sel == "h":
            rc, out, _ = spin("Reading run history", f"oruns {ctx.name}")
            print()
            for l in out.splitlines():
                print("  " + l)
        elif sel == "f":
            print(dim("  Opening... close the window to come back."))
            subprocess.run(["zsh", "-c", f"source {TOOLS_SH}; ogui final {ctx.name}"], capture_output=True)
        elif sel == "w":
            open_report(ctx)
        elif sel == "y":
            run_yosys(ctx, "rtl")
        elif sel == "k":
            open_klayout(ctx, False)
        elif sel == "3d":
            open_klayout(ctx, True)
        elif sel == "c":
            while True:
                v = ask("New clock period in ns", "", nav=False)
                try:
                    if float(v) > 0:
                        break
                except ValueError:
                    pass
                if v == "":
                    break
                print(rose("  ✗ Type a number such as 3.0"))
            if v:
                spin("Updating constraint.sdc", f"operiod {v} {ctx.name}")
                print(amber("  Clock updated. Steps show ⚠ until you rebuild (use r)."))
        elif sel == "x":
            if ask("Delete all results and logs for this project? (y/N)", "n", nav=False).lower().startswith("y"):
                spin("Cleaning", f"oclean {ctx.name}")
                print(green("  ✓ clean slate"))
        elif sel:
            print(rose("  ✗ Not an option. Type a step number or one of the letters above."))

# ---------------- project setup ----------------
HINTS = {
    "sky130hd": "SkyWater 130 nm, the most popular open PDK",
    "nangate45": "45 nm teaching library, no extra setup",
    "asap7": "7 nm academic library",
    "gf180": "GlobalFoundries 180 nm",
    "ihp-sg13g2": "IHP 130 nm SiGe",
}

def pick_project(steps):
    PROJECTS.mkdir(parents=True, exist_ok=True)
    existing = sorted(p.name for p in PROJECTS.iterdir() if (p / "config.mk").exists())
    if existing:
        print("  " + dim("Existing projects: ") + ", ".join(existing))
    while True:
        name = ask("Project name (new, or an existing one to open)", nav=False)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
            break
        print(rose("  ✗ Use letters, digits and underscores, starting with a letter."))
    proj = PROJECTS / name
    if (proj / "config.mk").exists():
        m = re.search(r"PLATFORM\s*=\s*(\S+)", (proj / "config.mk").read_text(errors="replace"))
        plat = m.group(1) if m else "?"
        print(green(f"  ✓ opening project {name} ({plat})"))
        return name, plat, False
    avail = [d.name for d in (FLOW / "platforms").iterdir() if (d / "config.mk").exists()]
    order = [p for p in HINTS if p in avail] + [p for p in sorted(avail) if p not in HINTS]
    print()
    for k, p in enumerate(order, 1):
        print(f"   {k}. {p:<12} {dim(HINTS.get(p, ''))}")
    while True:
        sel = ask("Platform (number or name)", "1", nav=False)
        plat = order[int(sel) - 1] if sel.isdigit() and 1 <= int(sel) <= len(order) else sel
        if plat in avail:
            break
        print(rose("  ✗ Not a platform I know. Pick one from the list."))
    while True:
        clk = ask("Target clock period in ns", "5.0", nav=False)
        try:
            if float(clk) > 0:
                break
        except ValueError:
            pass
        print(rose("  ✗ Type a number such as 5.0"))
    rc, out, _ = spin("Creating project", f"onew {name} {plat} {clk}")
    if rc != 0:
        print(rose("  ✗ Could not create the project:"))
        print(out)
        sys.exit(1)
    for st in steps:
        if st.get("stub"):
            path = proj / st["file"].replace("{name}", name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(stub_text(st, name))
    print(green(f"  ✓ created {proj}"))
    return name, plat, True

def main():
    for f in (TOOLS_SH, WIZ / "flow.json"):
        if not f.exists():
            print(f"Missing {f}. Re-run the installer."); sys.exit(1)
    cfg = json.loads((WIZ / "flow.json").read_text(errors="replace"))
    steps = cfg["steps"]
    if TTY:
        os.system("clear")
    print(teal(bold(f"\n  {cfg['title']}")))
    print(dim(f"  {cfg['subtitle']}\n"))
    name, plat, new = pick_project(steps)
    ctx = SimpleNamespace(name=name, plat=plat, proj=PROJECTS / name)
    if new:
        guided(ctx, steps, 0)
    else:
        print(dim("  Showing the project hub. Press a to continue the guided walk."))
    hub(ctx, steps)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(); bye()
