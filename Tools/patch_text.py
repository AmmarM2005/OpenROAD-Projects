#!/usr/bin/env python3
"""Patch 4: finish the clean KLayout view: hide text objects, hide blockage/option/waffle layers.
Backs up first, aborts if an anchor is not found exactly once, rolls back by itself if zsh -n fails."""
import os, shutil, subprocess, sys, time
from pathlib import Path

BASE = Path(os.environ.get("ORFS_ROOT") or (Path.home() / "Ammar_Linux" / "OpenROAD"))
SH = BASE / "Tools" / "orfs-tools.sh"
BK = BASE / "Archive" / "encfix"
stamp = time.strftime("%Y%m%d-%H%M%S")
HELPER = '#!/usr/bin/env python3\n"""oclean_lyp.py <platform.lyp> <out.lyp> : copy a KLayout layer-properties file with label, pin, net,\nboundary, cut, resistor, probe, short and model layers hidden, so a layout opens readable."""\nimport re, sys\nimport xml.etree.ElementTree as ET\n\nHIDE = re.compile(r"\\.(label|pin|net|res|cut|bound\\w*|probe|short|model|hv|text|dnwell|blockage|option\\d|waffleDrop)\\b|prBoundary|areaid|\\btext\\b|label|\\bpin\\b|blockage|waffleDrop", re.I)\n\ndef main(src, dst):\n    tree = ET.parse(src)\n    hidden = total = 0\n    for props in tree.getroot().iter("properties"):\n        name = (props.findtext("name") or props.findtext("source") or "")\n        vis = props.find("visible")\n        if vis is None or not name:\n            continue\n        total += 1\n        if HIDE.search(name):\n            vis.text = "false"\n            hidden += 1\n    tree.write(dst, encoding="utf-8", xml_declaration=True)\n    print(f"{hidden} of {total} layers hidden")\n\nif __name__ == "__main__":\n    if len(sys.argv) != 3:\n        sys.exit("usage: oclean_lyp.py <in.lyp> <out.lyp>")\n    main(sys.argv[1], sys.argv[2])\n'
RB = '# notext.rb : hide text objects (net/pin/instance labels) so the layout is readable; View > Show Text brings them back\nbegin\n  RBA::Application.instance.main_window.set_config("text-visible", "false")\nrescue => e\n  puts "notext.rb: #{e}"\nend\n'

B1_OLD = '  QT_QPA_PLATFORM=xcb klayout "${args[@]}"\n}\n'
B1_NEW = '  _okl_run "${args[@]}"\n}\n'
B2_OLD = '    QT_QPA_PLATFORM=xcb klayout "${args[@]}"\n  fi\n'
B2_NEW = '    _okl_run "${args[@]}"\n  fi\n'


B3_OLD = "_oclean_lyp() {"
B3_NEW = """_okl_run() {   # KLayout (plain 2D view) with text objects hidden unless OSHOW_ALL=1
  local -a nt
  [[ -z "${OSHOW_ALL:-}" ]] && nt=(-rm "$ORFS_TOOLS/notext.rb")
  QT_QPA_PLATFORM=xcb klayout "$@" "${nt[@]}"
}
_oclean_lyp() {"""


def once(t, o, l):
    n = t.count(o)
    if n != 1:
        print(f"ABORT: anchor '{l}' found {n} times (expected 1). Nothing was changed.")
        sys.exit(1)


t = SH.read_text(encoding="utf-8")
once(t, B1_OLD, "okl")
once(t, B2_OLD, "oshow")
once(t, B3_OLD, "_oclean_lyp")
BK.mkdir(parents=True, exist_ok=True)
b = BK / f"orfs-tools.sh.before-notext.{stamp}"
shutil.copy2(SH, b)
print(f"backup: {b}")
(BASE / "Tools" / "oclean_lyp.py").write_text(HELPER, encoding="utf-8")
(BASE / "Tools" / "notext.rb").write_text(RB, encoding="utf-8")
SH.write_text(t.replace(B1_OLD, B1_NEW).replace(B2_OLD, B2_NEW).replace(B3_OLD, B3_NEW), encoding="utf-8")
r = subprocess.run(["zsh", "-n", str(SH)], capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr)
    shutil.copy2(b, SH)
    print("ROLLED BACK (zsh -n failed)")
    sys.exit(1)
print("zsh -n: OK")
for f in (BASE / "Tmp").glob("clean-*.lyp"):
    f.unlink()
print("old cleaned layer files removed (they are rebuilt on next open)")
env = "unalias -a 2>/dev/null; export ORFS_ROOT=" + str(BASE) + "; source " + str(SH) + ";"
r = subprocess.run(["zsh", "-c", env + " otest quick"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("\n".join((r.stdout + r.stderr).rstrip("\n").splitlines()[-2:]))
print("\nRollback if needed:")
print(f"  cp -v {b} {SH}")
