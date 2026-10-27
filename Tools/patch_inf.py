#!/usr/bin/env python3
"""Patch 5 (from gate D): a run whose slack is INF (no constrained timing paths) must not say ALL CLEAR,
and an SDC clock port missing from the RTL is now a preflight FAIL instead of a warning.
Backs up first, aborts if an anchor is not found exactly once, rolls back by itself if zsh -n fails."""
import os, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(os.environ.get("ORFS_ROOT") or (Path.home() / "Ammar_Linux" / "OpenROAD"))
SH = BASE / "Tools" / "orfs-tools.sh"
BK = BASE / "Archive" / "encfix"
stamp = time.strftime("%Y%m%d-%H%M%S")

C1_OLD = '''  elif awk -v s="$SLACK" 'BEGIN{exit !(s<0)}'; then
    echo "✗ TIMING FAILED:'''
C1_NEW = '''  elif [[ ! "$SLACK" =~ '^-?[0-9]+(\\.[0-9]+)?$' ]]; then
    echo "⚠ TIMING NOT CHECKED: slack is '$SLACK' (no constrained paths). Does the clock port in constraint.sdc exist in the RTL? (ocheck)"
  elif awk -v s="$SLACK" 'BEGIN{exit !(s<0)}'; then
    echo "✗ TIMING FAILED:'''
C2_OLD = '''        print "  WARN: the SDC clocks port '$clkport' but no RTL file mentions it"
        print "        (a purely combinational design needs a clk port too, or a virtual clock in the SDC)"
'''
C2_NEW = '''        print "  FAIL: the SDC clocks port '$clkport' but no RTL file mentions it"
        print "        (name the clock input in the RTL exactly as in constraint.sdc, otherwise timing is never checked)"
        (( errors += 1 ))
'''


def once(t, o, l):
    n = t.count(o)
    if n != 1:
        print(f"ABORT: anchor '{l}' found {n} times (expected 1). Nothing was changed.")
        sys.exit(1)


t = SH.read_text(encoding="utf-8")
once(t, C1_OLD, "osum verdict")
once(t, C2_OLD, "ocheck clock warning")
BK.mkdir(parents=True, exist_ok=True)
b = BK / f"orfs-tools.sh.before-inf.{stamp}"
shutil.copy2(SH, b)
print(f"backup: {b}")
SH.write_text(t.replace(C1_OLD, C1_NEW).replace(C2_OLD, C2_NEW), encoding="utf-8")
r = subprocess.run(["zsh", "-n", str(SH)], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr)
    shutil.copy2(b, SH)
    print("ROLLED BACK (zsh -n failed)")
    sys.exit(1)
print("zsh -n: OK")
env = "unalias -a 2>/dev/null; export ORFS_ROOT=" + str(BASE) + "; source " + str(SH) + ";"
r = subprocess.run(["zsh", "-c", env + " otest quick"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("\n".join((r.stdout + r.stderr).rstrip("\n").splitlines()[-2:]))
print("\nRollback if needed:")
print(f"  cp -v {b} {SH}")
