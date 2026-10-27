#!/usr/bin/env zsh
# Gate (d): failure and recovery tests on a throwaway project (zzfail). Real projects are never touched.
unalias -a 2>/dev/null
source /home/ammar/Ammar_Linux/OpenROAD/Tools/orfs-tools.sh
P="$ORFS_PROJECTS/zzfail"
hdr() { echo; echo "################ $1"; }
saved() { [[ -e "$P/out/latest" || -s "$P/out/runs.tsv" && $(wc -l < "$P/out/runs.tsv") -gt 1 ]] && echo "RESULT: a run WAS saved (not expected)" || echo "RESULT: no run saved (good)"; }
[[ -e "$P" ]] && { echo "zzfail already exists, stopping (remove it first)"; exit 1; }
onew zzfail sky130hd 5.0 >/dev/null || { echo "onew failed"; exit 1; }
cp "$P/rtl/zzfail.v" "$P/zzfail.v.good"
cp "$P/constraint.sdc" "$P/constraint.sdc.good"
good() { cp "$P/zzfail.v.good" "$P/rtl/zzfail.v"; cp "$P/constraint.sdc.good" "$P/constraint.sdc"; }

hdr "A. constraint.sdc missing"
rm "$P/constraint.sdc"
ocheck zzfail; echo "ocheck exit: $?"
orun zzfail 2>&1 | tail -6; echo "orun exit: ${pipestatus[1]}"
saved; good

hdr "B. top module name does not match DESIGN_NAME"
sed -i 's/^module zzfail/module zzwrong/' "$P/rtl/zzfail.v"
ocheck zzfail; echo "ocheck exit: $?"
orun zzfail 2>&1 | tail -6; echo "orun exit: ${pipestatus[1]}"
saved; good

hdr "C. SDC clocks a port the RTL does not have"
sed -i 's/get_ports clk/get_ports ckx/' "$P/constraint.sdc"
ocheck zzfail; echo "ocheck exit: $?"
orun zzfail 2>&1 | tail -14; echo "orun exit: ${pipestatus[1]}"
saved; good

hdr "D. Verilog syntax error"
sed -i 's/^endmodule/endmodul/' "$P/rtl/zzfail.v"
ocheck zzfail | tail -3
orun zzfail 2>&1 | tail -14; echo "orun exit: ${pipestatus[1]}"
saved; good

hdr "E. run killed half way, then recovery"
( orun zzfail >/dev/null 2>&1 ) &
pid=$!
sleep 10
pkill -KILL -P $pid 2>/dev/null; kill -KILL $pid 2>/dev/null
sleep 1; pkill -KILL -f zzfail 2>/dev/null; sleep 2
echo "stages after the kill:"; ostat zzfail
saved
echo "--- recovery: clean build of the good design ---"
ofresh zzfail 2>&1 | tail -14
oruns zzfail

hdr "F. cleanup (project archived first)"
oclean zzfail >/dev/null 2>&1
T="$ORFS_ROOT/Archive/zzfail-gate-d.$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$T" -C "$ORFS_PROJECTS" zzfail && tar -tzf "$T" >/dev/null && echo "archive: $T" && rm -rf "$P"
for d in results logs reports objects; do rm -rf "$ORFS_FLOW/$d/sky130hd/zzfail"; done
echo "projects now:"; ls -1 "$ORFS_PROJECTS"
echo; echo "GATE D DONE"
