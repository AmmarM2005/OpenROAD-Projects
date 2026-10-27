#!/usr/bin/env python3
"""Patch 2 for the OpenROAD toolkit:
  1. plain-English error explainer (_oexplain), called when a make step fails
  2. ocheck: warns when the SDC clock port is not in the RTL
  3. orun: preflight also runs from a sub-folder of a project, and a project name is never confused with a folder of the same name in the current directory
  4. o25d: the two broken duplicate definitions become a thin wrapper around o3d
  5. test_oreport.py: import works when run from anywhere
  6. otest: three new checks for the explainer
Backs up first, aborts without writing if any anchor is not found exactly once, rolls back by itself if a syntax check fails."""
import os, re, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(os.environ.get("ORFS_ROOT") or (Path.home() / "Ammar_Linux" / "OpenROAD"))
SH = BASE / "Tools" / "orfs-tools.sh"
TR = BASE / "Tools" / "test_oreport.py"
BK = BASE / "Archive" / "encfix"
PROJ = os.environ.get("PATCH_VERIFY_PROJECT", "mux41")
stamp = time.strftime("%Y%m%d-%H%M%S")

# ---------------------------------------------------------------- edits to orfs-tools.sh
E1_OLD = '''_omake() {   # _omake <projdir> <make targets...>   (output goes to <project>/make.log)
'''
E1_NEW = r'''_oexplain() {   # _oexplain <make.log> : plain-English hints for common failures (prints nothing when nothing matches)
  local log="$1" i n=0
  local -a rules
  [[ -f "$log" ]] || return 0
  rules=(
    'syntax error|parse error'
      "your Verilog has a syntax error."
      "fix the line named in the error above (in rtl/), then run again. osim finds syntax errors quickly."
    'ERROR: Module .* not found|top module .* not found|is not part of the design'
      "the top module name does not match DESIGN_NAME."
      "make DESIGN_NAME in config.mk equal your top 'module' name (ocheck <project> shows both)."
    'No rule to make target'
      "a file named in config.mk is missing (usually constraint.sdc or an RTL file)."
      "check that rtl/*.v and constraint.sdc exist (ocheck <project>)."
    'GRT-0116|GRT-0118|stubborn tiles'
      "routing ran out of room (congestion)."
      "enlarge DIE_AREA and CORE_AREA in config.mk (for example 120 -> 200), then ofresh."
    '\[ERROR (IFP|PDN)-'
      "the floorplan or power grid could not be built, usually because the die is too small."
      "check DIE_AREA / CORE_AREA in config.mk (the core must sit inside the die), then ofresh."
    "STA-0366|No ports matched|port '[^']*' not found"
      "the SDC refers to a port the design does not have (usually the clock)."
      "name the clock input in your RTL exactly as in constraint.sdc (default: clk)."
    'No space left on device'
      "the disk is full."
      "free space under /home (oprune old runs, oclean unused projects), then retry."
    'Cannot allocate memory|std::bad_alloc|Out of memory|^Killed'
      "the flow ran out of memory."
      "close other programs and retry."
  )
  for (( i = 1; i <= ${#rules}; i += 3 )); do
    (( n >= 3 )) && break
    if grep -q -i -E -- "${rules[i]}" "$log" 2>/dev/null; then
      echo "  ➜ what happened: ${rules[i+1]}"
      echo "    how to fix   : ${rules[i+2]}"
      n=$((n+1))
    fi
  done
  return 0
}
_omake() {   # _omake <projdir> <make targets...>   (output goes to <project>/make.log)
'''

E2_OLD = '''    grep -n -i -E "error|\\*\\*\\*" "$log" | head -8
    return 1
'''
E2_NEW = '''    grep -n -i -E "error|\\*\\*\\*" "$log" | head -8
    _oexplain "$log"
    return 1
'''

E3_OLD = '''  if (( errors > 0 )); then
    print "Preflight result: FAIL ($errors issue(s))"
'''
E3_NEW = r'''  # The clock port named in the SDC must exist in the RTL
  if [[ -f "$sdc" && -d "$p/rtl" ]]; then
    local clkport
    clkport="$(sed -nE 's/^[[:space:]]*create_clock.*get_ports[[:space:]]+\{?([A-Za-z_][A-Za-z0-9_]*)\}?.*/\1/p' "$sdc" | head -1)"
    if [[ -n "$clkport" ]]; then
      if grep -rqw --include='*.v' --include='*.sv' -- "$clkport" "$p/rtl" 2>/dev/null; then
        print "  PASS: clock port '$clkport' from the SDC appears in the RTL"
      else
        print "  WARN: the SDC clocks port '$clkport' but no RTL file mentions it"
        print "        (a purely combinational design needs a clk port too, or a virtual clock in the SDC)"
      fi
    fi
  fi

  if (( errors > 0 )); then
    print "Preflight result: FAIL ($errors issue(s))"
'''

E4_OLD = '''          "$candidate" != */* ]]; then
      project="$candidate"
'''
E4_NEW = '''          "$candidate" != */* ]]; then
      project="$ORFS_PROJECTS/$candidate"
'''

E5_OLD = '''  elif [[ -f "$PWD/config.mk" ]]; then
    ocheck "$PWD" || return $?
  fi
'''
E5_NEW = '''  elif [[ -z "$candidate" ]]; then
    # no argument: find the project the same way the other commands do (walks up from the current folder)
    local up
    up="$(_oproj "" 2>/dev/null)" && { ocheck "$up" || return $?; }
  fi
'''

E6_MARK = "# 2.5D / 3D Viewer shorthand: o25d <project>\n"
E6_NEW = '''# 2.5D view shorthand: o25d <project> opens the KLayout 2.5D view (same as o3d).
# Accepts "foo", "Projects/foo" or "Projects/foo/".
o25d() {
  local t="${1#Projects/}"
  t="${t%/}"
  o3d "$t"
}
'''

E7_OLD = '''  _ot "no run is saved after a failure" test ! -e "$tp/out/latest"
'''
E7_NEW = r'''  _ot "no run is saved after a failure" test ! -e "$tp/out/latest"
  printf '%s\n' "ERROR: syntax error, unexpected '}'" > "$workspace/ex_a.log"
  printf '%s\n' "make: *** No rule to make target '/x/constraint.sdc'.  Stop." > "$workspace/ex_b.log"
  printf '%s\n' "everything is fine here" > "$workspace/ex_c.log"
  _ot "error explainer spots a Verilog syntax error" test -n "$(_oexplain "$workspace/ex_a.log" | grep -i 'syntax')"
  _ot "error explainer spots a missing file" test -n "$(_oexplain "$workspace/ex_b.log" | grep -i 'missing')"
  _ot "error explainer stays quiet on a clean log" test -z "$(_oexplain "$workspace/ex_c.log")"
'''

# ---------------------------------------------------------------- edits to test_oreport.py
T1_OLD = "from Tools.oreport import generate_ppa_charts\n#!/usr/bin/env python3\n"
T1_NEW = "#!/usr/bin/env python3\n"
T2_OLD = 'GENERATOR = Path(__file__).resolve().with_name("oreport.py")\n'
T2_NEW = ('GENERATOR = Path(__file__).resolve().with_name("oreport.py")\n'
          'sys.path.insert(0, str(Path(__file__).resolve().parent))\n'
          'from oreport import generate_ppa_charts  # noqa: E402\n')


def once(text, old, label, where):
    n = text.count(old)
    if n != 1:
        print(f"ABORT: anchor '{label}' found {n} times in {where} (expected 1). Nothing was changed.")
        sys.exit(1)


sh_t = SH.read_text(encoding="utf-8")
tr_t = TR.read_text(encoding="utf-8")

for old, label in ((E1_OLD, "_omake header"), (E2_OLD, "_omake failure branch"), (E3_OLD, "ocheck result"),
                   (E4_OLD, "orun project name"), (E5_OLD, "orun walk-up"), (E6_MARK, "o25d marker"),
                   (E7_OLD, "otest failure checks")):
    once(sh_t, old, label, "orfs-tools.sh")
once(tr_t, T1_OLD, "test import line", "test_oreport.py")
once(tr_t, T2_OLD, "GENERATOR line", "test_oreport.py")

idx = sh_t.index(E6_MARK)
names = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\(\) \{", sh_t[idx:], re.M)
if names != ["o25d", "o25d"]:
    print(f"ABORT: expected only the two o25d definitions after the marker, found {names}. Nothing was changed.")
    sys.exit(1)

BK.mkdir(parents=True, exist_ok=True)
b_sh = BK / f"orfs-tools.sh.before-review.{stamp}"
b_tr = BK / f"test_oreport.py.before-review.{stamp}"
shutil.copy2(SH, b_sh)
shutil.copy2(TR, b_tr)
print(f"backups:\n  {b_sh}\n  {b_tr}")

new_sh = sh_t[:idx].replace(E1_OLD, E1_NEW).replace(E2_OLD, E2_NEW).replace(E3_OLD, E3_NEW) \
    .replace(E4_OLD, E4_NEW).replace(E5_OLD, E5_NEW).replace(E7_OLD, E7_NEW) + E6_NEW
new_tr = tr_t.replace(T1_OLD, T1_NEW).replace(T2_OLD, T2_NEW)
SH.write_text(new_sh, encoding="utf-8")
TR.write_text(new_tr, encoding="utf-8")


def rollback(why):
    shutil.copy2(b_sh, SH)
    shutil.copy2(b_tr, TR)
    print(f"ROLLED BACK ({why}). Both files restored.")
    sys.exit(1)


r = subprocess.run(["zsh", "-n", str(SH)], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr)
    rollback("zsh -n failed")
print("zsh -n: OK")
r = subprocess.run([sys.executable, "-m", "py_compile", str(TR)], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr)
    rollback("py_compile failed")
print("py_compile: OK")

env = "unalias -a 2>/dev/null; export ORFS_ROOT=%s; source %s;" % (BASE, SH)


def zrun(script, tail=None):
    r = subprocess.run(["zsh", "-c", env + " " + script], capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).rstrip("\n")
    if tail:
        out = "\n".join(out.splitlines()[-tail:])
    return out


print("\n=== o25d is now a thin wrapper (one definition) ===")
print(zrun("whence -w o25d; functions o25d | head -8"))

print("\n=== error explainer on three sample logs ===")
print(zrun(r'''
t=$(mktemp -d)
printf '%s\n' "ERROR: Module \`foo' not found!" "[ERROR GRT-0116] Global routing finished with congestion." > $t/a.log
printf '%s\n' "all good" > $t/b.log
echo "--- log with two known problems ---"; _oexplain $t/a.log
echo "--- clean log (expect nothing) ---"; _oexplain $t/b.log
rm -rf $t
'''))

print("\n=== ocheck %s (new clock-port line) ===" % PROJ)
print(zrun("ocheck %s" % PROJ))

print("\n=== test_oreport.py ===")
r = subprocess.run([sys.executable, "-I", str(TR)], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("\n".join((r.stdout + r.stderr).rstrip("\n").splitlines()[-6:]))

print("\n=== otest quick ===")
out = zrun("otest quick", tail=8)
print(out)
if "0 failed" not in out:
    print("otest reported failures. Rolling back is advised.")

print("\nRollback if needed:")
print(f"  cp -v {b_sh} {SH}")
print(f"  cp -v {b_tr} {TR}")
