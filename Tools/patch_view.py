#!/usr/bin/env python3
"""Patch 3: KLayout opens with a clean layer view (labels, pins, nets, boundaries hidden).
Set OSHOW_ALL=1 to get the full platform layer set. Backs up first, aborts if an anchor is not found exactly once,
rolls back by itself if a syntax check fails."""
import os, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(os.environ.get("ORFS_ROOT") or (Path.home() / "Ammar_Linux" / "OpenROAD"))
SH = BASE / "Tools" / "orfs-tools.sh"
HP = BASE / "Tools" / "oclean_lyp.py"
BK = BASE / "Archive" / "encfix"
stamp = time.strftime("%Y%m%d-%H%M%S")
HELPER = '#!/usr/bin/env python3\n"""oclean_lyp.py <platform.lyp> <out.lyp> : copy a KLayout layer-properties file with label, pin, net,\nboundary, cut, resistor, probe, short and model layers hidden, so a layout opens readable."""\nimport re, sys\nimport xml.etree.ElementTree as ET\n\nHIDE = re.compile(r"\\.(label|pin|net|res|cut|bound\\w*|probe|short|model|hv|text|dnwell)\\b|prBoundary|areaid|\\btext\\b|label|\\bpin\\b", re.I)\n\ndef main(src, dst):\n    tree = ET.parse(src)\n    hidden = total = 0\n    for props in tree.getroot().iter("properties"):\n        name = (props.findtext("name") or "")\n        vis = props.find("visible")\n        if vis is None or not name:\n            continue\n        total += 1\n        if HIDE.search(name):\n            vis.text = "false"\n            hidden += 1\n    tree.write(dst, encoding="utf-8", xml_declaration=True)\n    print(f"{hidden} of {total} layers hidden")\n\nif __name__ == "__main__":\n    if len(sys.argv) != 3:\n        sys.exit("usage: oclean_lyp.py <in.lyp> <out.lyp>")\n    main(sys.argv[1], sys.argv[2])\n'

A1_OLD = "_okl_common() {   # sets KL_P KL_NAME KL_PLAT KL_GDS KL_LYP\n"
A1_NEW = """_oclean_lyp() {   # _oclean_lyp <platform.lyp> : echo a cleaned copy (labels/pins/boundaries hidden); the original if OSHOW_ALL=1 or on any problem
  local src="$1" out
  [[ -n "$src" && -z "${OSHOW_ALL:-}" ]] || { echo "$src"; return; }
  out="$ORFS_ROOT/Tmp/clean-${src:h:t}.lyp"
  mkdir -p "$ORFS_ROOT/Tmp"
  if [[ ! -s "$out" || "$src" -nt "$out" || "$ORFS_TOOLS/oclean_lyp.py" -nt "$out" ]]; then
    python3 -I "$ORFS_TOOLS/oclean_lyp.py" "$src" "$out" >/dev/null 2>&1 || { echo "$src"; return; }
  fi
  [[ -s "$out" ]] && echo "$out" || echo "$src"
}
_okl_common() {   # sets KL_P KL_NAME KL_PLAT KL_GDS KL_LYP
"""
A2_OLD = 'lyps=("$ORFS_FLOW/platforms/$KL_PLAT"/*.lyp(N)); KL_LYP="${lyps[1]:-}"\n'
A2_NEW = 'lyps=("$ORFS_FLOW/platforms/$KL_PLAT"/*.lyp(N)); KL_LYP="$(_oclean_lyp "${lyps[1]:-}")"\n'
A3_OLD = '  [[ -n "${lyps[1]:-}" ]] && args+=(-l "${lyps[1]}")\n  echo "▶ ${run:t}"\n'
A3_NEW = '  [[ -n "${lyps[1]:-}" ]] && args+=(-l "$(_oclean_lyp "${lyps[1]}")")\n  echo "▶ ${run:t}${OSHOW_ALL:+  (all layers)}"\n'


def once(t, o, l):
    n = t.count(o)
    if n != 1:
        print(f"ABORT: anchor '{l}' found {n} times (expected 1). Nothing was changed.")
        sys.exit(1)


t = SH.read_text(encoding="utf-8")
for o, l in ((A1_OLD, "_okl_common"), (A2_OLD, "KL_LYP line"), (A3_OLD, "oshow lyp line")):
    once(t, o, l)
BK.mkdir(parents=True, exist_ok=True)
b = BK / f"orfs-tools.sh.before-cleanview.{stamp}"
shutil.copy2(SH, b)
print(f"backup: {b}")
HP.write_text(HELPER, encoding="utf-8")
SH.write_text(t.replace(A1_OLD, A1_NEW).replace(A2_OLD, A2_NEW).replace(A3_OLD, A3_NEW), encoding="utf-8")

r = subprocess.run(["zsh", "-n", str(SH)], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr)
    shutil.copy2(b, SH)
    print("ROLLED BACK (zsh -n failed)")
    sys.exit(1)
print("zsh -n: OK")

env = "unalias -a 2>/dev/null; export ORFS_ROOT=" + str(BASE) + "; source " + str(SH) + ";"


def zrun(s, tail=None):
    r = subprocess.run(["zsh", "-c", env + " " + s], capture_output=True, text=True, encoding="utf-8", errors="replace")
    o = (r.stdout + r.stderr).rstrip("\n")
    return "\n".join(o.splitlines()[-tail:]) if tail else o


print("\n=== cleaned layer file for sky130hd ===")
print(zrun('l=($ORFS_FLOW/platforms/sky130hd/*.lyp(N)); c=$(_oclean_lyp ${l[1]}); echo "$c"; python3 -I $ORFS_TOOLS/oclean_lyp.py ${l[1]} /dev/null 2>&1; grep -c "<visible>false" "$c"'))
print("\n=== otest quick ===")
print(zrun("otest quick", tail=3))
print("\nRollback if needed:")
print(f"  cp -v {b} {SH}")
