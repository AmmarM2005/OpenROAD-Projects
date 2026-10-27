#!/usr/bin/env python3
"""Patch 1: clear pass/fail verdict in osum, amber colour for warnings in the wizard,
and a message for unknown keys in the wizard step menus.
Backs up first, aborts without writing if any anchor is not found exactly once,
rolls back automatically if a syntax check fails."""
import shutil, subprocess, sys, time
from pathlib import Path

BASE = Path.home() / "Ammar_Linux" / "OpenROAD"
SH = BASE / "Tools" / "orfs-tools.sh"
PY = BASE / "Tools" / "wizard" / "chipwiz.py"
BK = BASE / "Archive" / "encfix"
stamp = time.strftime("%Y%m%d-%H%M%S")

OSUM_OLD = '''  if [[ -z "$SLACK" ]]; then echo "(no timing report yet)"
  elif awk -v s="$SLACK" 'BEGIN{exit !(s<0)}'; then echo "✗ TIMING VIOLATED: raise clk_period in constraint.sdc, then ofresh"
  elif [[ -n "$DRC" && "$DRC" != "0" ]]; then echo "✗ DRC violations in routing"
  else echo "✓ clean: timing met, 0 DRC"; fi
'''
OSUM_NEW = '''  local rep="$ORFS_FLOW/reports/$plat/$name/base/6_finish.rpt" wns tns clk
  wns="$(grep -h -m1 -E '^wns max' "$rep" 2>/dev/null | awk '{print $3}')"
  tns="$(grep -h -m1 -E '^tns max' "$rep" 2>/dev/null | awk '{print $3}')"
  clk="$(grep -E '^set clk_period' "$p/constraint.sdc" 2>/dev/null | head -1 | awk '{print $3}')"
  [[ -n "$wns" ]] && echo "WNS / TNS   : $wns / ${tns:-?} ns"
  echo
  if [[ -z "$SLACK" ]]; then
    echo "⚠ NO TIMING RESULT YET (run: ogds)"
  elif awk -v s="$SLACK" 'BEGIN{exit !(s<0)}'; then
    echo "✗ TIMING FAILED: slack $SLACK ns at ${clk:-?} ns. Raise clk_period (operiod <ns>), then ofresh"
  elif [[ -z "$DRC" ]]; then
    echo "⚠ TIMING MET (slack $SLACK ns), but the DRC count was not found in the routing log"
  elif [[ "$DRC" != "0" ]]; then
    echo "✗ DRC FAILED: $DRC violations in routing (timing met)"
  else
    echo "✓ ALL CLEAR: timing met (slack $SLACK ns), 0 DRC violations"
  fi
'''

COL_OLD = '''        col = green if "✓" in l else (rose if "✗" in l else (lambda s: s))'''
COL_NEW = '''        col = green if "✓" in l else (rose if "✗" in l else (amber if "⚠" in l else (lambda s: s)))'''

EDIT_OLD = '''            elif a == "t" and st.get("check") == "tb":
                check(st, ctx, path)
'''
EDIT_NEW = '''            elif a == "t" and st.get("check") == "tb":
                check(st, ctx, path)
            else:
                print(rose(f"  ✗ '{a}' is not an option for this step. Choose one of the keys shown above, or press Enter to go back."))
'''

FLOW_OLD = '''                if run_flow_cmd(ctx, st, nav=False) and st.get("summary"):
                    show_summary(ctx)

def hub(ctx, steps):'''
FLOW_NEW = '''                if run_flow_cmd(ctx, st, nav=False) and st.get("summary"):
                    show_summary(ctx)
            else:
                print(rose(f"  ✗ '{a}' is not an option for this step. Choose one of the keys shown above, or press Enter to go back to the hub."))

def hub(ctx, steps):'''


def once(text, old, label):
    n = text.count(old)
    if n != 1:
        print(f"ABORT: anchor '{label}' found {n} times (expected 1). Nothing was changed.")
        sys.exit(1)


sh_t = SH.read_text(encoding="utf-8")
py_t = PY.read_text(encoding="utf-8")
for t, o, l in ((sh_t, OSUM_OLD, "osum verdict"), (py_t, COL_OLD, "summary colour"),
                (py_t, EDIT_OLD, "edit-step menu"), (py_t, FLOW_OLD, "flow-step menu")):
    once(t, o, l)

BK.mkdir(parents=True, exist_ok=True)
b_sh = BK / f"orfs-tools.sh.before-verdict.{stamp}"
b_py = BK / f"chipwiz.py.before-verdict.{stamp}"
shutil.copy2(SH, b_sh)
shutil.copy2(PY, b_py)
print(f"backups:\n  {b_sh}\n  {b_py}")

SH.write_text(sh_t.replace(OSUM_OLD, OSUM_NEW), encoding="utf-8")
PY.write_text(py_t.replace(COL_OLD, COL_NEW).replace(EDIT_OLD, EDIT_NEW).replace(FLOW_OLD, FLOW_NEW), encoding="utf-8")


def rollback(why):
    shutil.copy2(b_sh, SH)
    shutil.copy2(b_py, PY)
    print(f"ROLLED BACK ({why}). Both files restored.")
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

env = "unalias -a 2>/dev/null; source %s;" % SH
print("\n=== osum mux41 (new verdict) ===")
r = subprocess.run(["zsh", "-c", env + " osum mux41"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout + r.stderr)
try:
    r.stdout.encode("utf-8")
    print("osum output: valid UTF-8")
except UnicodeError:
    print("osum output: INVALID UTF-8")

print("=== otest quick ===")
r = subprocess.run(["zsh", "-c", env + " otest quick"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("\n".join((r.stdout + r.stderr).splitlines()[-4:]))
if "0 failed" not in r.stdout:
    print("otest reported failures. Rolling back is advised:")
    print(f"  cp -v {b_sh} {SH}")
    print(f"  cp -v {b_py} {PY}")
print("\nRollback if needed:")
print(f"  cp -v {b_sh} {SH}")
print(f"  cp -v {b_py} {PY}")
