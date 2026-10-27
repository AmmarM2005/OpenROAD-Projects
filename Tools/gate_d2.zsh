#!/usr/bin/env zsh
# Gate (d) retest: C (bad clock port) and E (killed run) done properly on a throwaway project (zzfail2).
unalias -a 2>/dev/null
source /home/ammar/Ammar_Linux/OpenROAD/Tools/orfs-tools.sh
P="$ORFS_PROJECTS/zzfail2"
hdr() { echo; echo "################ $1"; }
[[ -e "$P" ]] && { echo "zzfail2 already exists, stopping"; exit 1; }
onew zzfail2 sky130hd 5.0 >/dev/null || { echo "onew failed"; exit 1; }

hdr "C. SDC clocks a port the RTL does not have (must stop before the flow)"
sed -i 's/get_ports clk/get_ports ckx/' "$P/constraint.sdc"
orun zzfail2 2>&1 | tail -5; echo "orun exit: ${pipestatus[1]}"
echo "runs saved: $(ls "$P/out/runs" 2>/dev/null | wc -l)  (expect 0)"
sed -i 's/get_ports ckx/get_ports clk/' "$P/constraint.sdc"

hdr "E. run killed half way, then recovery with plain orun"
( orun zzfail2 >/dev/null 2>&1 ) &
pid=$!
sleep 8
pkill -KILL -P $pid 2>/dev/null; kill -KILL $pid 2>/dev/null
sleep 1; pkill -KILL -f zzfail2 2>/dev/null; sleep 2
echo "stages after the kill (expect NOT all six done):"; ostat zzfail2
echo "runs saved: $(ls "$P/out/runs" 2>/dev/null | wc -l)  (expect 0)"
echo "--- recovery: plain orun, no clean ---"
orun zzfail2 2>&1 | tail -12
echo "runs saved: $(ls "$P/out/runs" 2>/dev/null | wc -l)  (expect 1)"

hdr "F. cleanup (archived first)"
oclean zzfail2 >/dev/null 2>&1
T="$ORFS_ROOT/Archive/zzfail2-gate-d.$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$T" -C "$ORFS_PROJECTS" zzfail2 && tar -tzf "$T" >/dev/null && echo "archive: $T" && rm -rf "$P"
for d in results logs reports objects; do rm -rf "$ORFS_FLOW/$d/sky130hd/zzfail2"; done
echo "projects now:"; ls -1 "$ORFS_PROJECTS"
echo; echo "GATE D2 DONE"
