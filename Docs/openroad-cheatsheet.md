# OpenROAD / ORFS cheat sheet (Ammar)

## Paths
- ORFS: ~/Ammar_Linux/OpenROAD/OpenROAD-flow-scripts/flow
- Yosys (new): ~/Ammar_Linux/oss-cad-suite/bin/yosys   (apt yosys 0.9 is too old)
- Env file: source ~/Ammar_Linux/orfs-env.sh   (YOSYS_EXE, OPENROAD_EXE, TMPDIR, QT_QPA_PLATFORM=xcb)

## Run a design (from flow/)
make DESIGN_CONFIG=./designs/<platform>/<name>/config.mk            # full flow RTL -> GDS
make DESIGN_CONFIG=... clean_all                                    # wipe results/logs/objects
make DESIGN_CONFIG=... gui_final                                    # open routed result in OpenROAD GUI
make DESIGN_CONFIG=... gui_floorplan | gui_place | gui_cts | gui_route

## Stages: synth -> floorplan -> place -> cts -> route -> final
Outputs: results/<plat>/<name>/base/  logs/.../base/  reports/.../base/
Final files: 6_final.odb 6_final.gds 6_final.def 6_final.v 6_final.sdc 6_final.spef

## OpenROAD GUI
- Display Control (left): layer/net/instance toggles; Heat Maps menu: congestion, IR drop
- Tcl box (bottom): report_checks -path_delay max
- Built-in 3D tab is EMPTY on this build -> use KLayout 2.5d instead

## KLayout 3D (2.5d view)
klayout <results/.../6_final.gds> -> Tools > 2.5d View > New 2.5d Script -> paste z(input(L,0), height: H) lines -> Run
nangate45 layers: metal1..10 = 11,13,15,...,29 (/0); vias 12,14,...,30; poly 9, active 1, contact 10

## Gotchas
- zsh aborts a whole command if a glob matches nothing (use ls / find instead)
- git log opens a pager: use git --no-pager
- Keep everything under /home (root partition is small)

## Lessons from sky130hd mux32 (first custom design)
- New design = 3 files: designs/src/<name>/<name>.v, designs/<plat>/<name>/config.mk, constraint.sdc
- kepler-formal missing (tools/install never built) -> add LEC_CHECK=0 to the make line
- Tiny designs: CORE_UTILIZATION makes a cramped die and detailed route loops on
  "stubborn tiles" (46+ iterations). Use explicit DIE_AREA / CORE_AREA instead (x0 y0 x1 y1, um)
- Slow vs hung: ps -eo pid,etime,pcpu,comm | grep openroad ; tail logs/<plat>/<name>/base/5_2_route.tmp.log
  High CPU + growing log = working. make | tail shows nothing until it ends.
- CTS skips a clock with 1 sink (CTS-0041). Register the inputs too if you want a real clock tree.
- grep -r over flow/scripts can hang; grep specific files instead.
- Pre-synthesis sim: oss-cad-suite/bin/iverilog + vvp (no apt installs needed)

## Handy OpenROAD Tcl (type in GUI Tcl box or openroad prompt)
report_checks -path_delay max      # worst setup path (add -path_delay min for hold)
report_wns / report_tns            # worst / total negative slack
report_design_area                 # area + utilization
report_cell_usage                  # cell-type breakdown (see what ORFS added after synth)
report_power                       # power estimate
report_clock_skew                  # after CTS
GUI Tcl box is NOT a shell: use exec ls ...
Experiments: change -period in constraint.sdc and rerun (clean_all first) to find the max frequency
sky130hd GDS: diff 65/20 poly 66/20 licon1 66/44 li1 67/20 mcon 67/44 met1 68/20 via 68/44
              met2 69/20 via2 69/44 met3 70/20 via3 70/44 met4 71/20 via4 71/44 met5 72/20

## Clock-period sweep (mux32r, sky130hd)
- Script: ~/Ammar_Linux/work/mux32r/sweep.sh <periods...>  (edits line 1 of constraint.sdc: set clk_period N, cleans, runs, prints area/power/slack/CTS/DRC)
- SDC with io_delay = 0.2*period keeps the constraint proportional
- Results: slack ~ 0.8*P - 1.08 (I/O-path limited), power ~ proportional to frequency, area +6% from 4.0 to 1.5 ns
- CTS: 38 sinks -> 5 clock buffers. Clock tree view: Windows > Clock Tree Viewer (gui_cts); Tcl: report_clock_skew

## mux32r timing limit (sky130hd, tt corner)
- Closes down to 1.4 ns (+0.05 slack); 1.3 ns = -0.03 (violated). slack ~ 0.8*P - 1.08 held across 1.0-4.0 ns.
- "flow: OK" does NOT mean timing met: ORFS finishes with negative slack. Check wns/tns in reports/.../6_finish.rpt.
- Cost of speed: area 1541 -> 1728 um2 and power 0.74 -> 3.2 mW from 4.0 ns to 1.0 ns.
- Tighter clock -> resizer upsizes cells; hold slack stayed +0.36..+0.54 in all runs.

## orfs-tools.sh (short commands) : type ohelp
onew <name> [plat] [clk] -> edit rtl/ tb/ constraint.sdc -> osim -> orun -> osum -> ogui / o3d
Stages: osyn ofp opl octs ort ogds ; sweep: osweep 4.0 3.0 2.0 ; after editing config.mk/SDC: ofresh
Projects live in ~/Ammar_Linux/projects/<name>/ (results/ logs/ reports/ are links into the ORFS flow dir)

## Guided wizard
Chip Designing OPENROAD  (any letter case) -> RTL, testbench, SDC, config.mk, then synth..GDSII with a GUI peek after each stage
Steps/text: ~/Ammar_Linux/tools/wizard/flow.json   Runner: chipwiz.py   Editor override: CHIPWIZ_EDITOR=nano

## Layout (since the reorganisation)
~/Ammar_Linux/OpenROAD/{OpenROAD-flow-scripts, Projects, Tools, Docs, Archive, Tmp}
Projects/<name>/{rtl, tb, constraint.sdc, config.mk, results->, logs->, reports->}
config.mk has a PROJ_DIR line the toolkit keeps correct, so projects can be moved. Toolkit: Tools/orfs-tools.sh (type ohelp)
Wizard: Chip Designing OPENROAD -> guided walk for new projects, hub for existing ones (number = open a step, a, r, s, f, 3d, c, x, q)
Guided prompts accept: b back, m menu, g<N> goto step N, q pause.  Old versions are in Archive/

## KLayout from the toolkit
okl [proj]   plain KLayout on 6_final.gds with the platform layer colours
o3d [proj]   KLayout + 2.5D view; stack auto-built by Tools/25d/gen25d.py (thickness from tech LEF, layers from the GDS) -> <proj>/3d/view25d.{lyd25,rb}
o3dgen       only generate and print the stack table.  Front-end layers (diff/poly/contact): Tools/25d/frontend.json
Wizard: at the GDSII step press k (KLayout) or 3 (2.5D); in the hub k / 3d.   KLayout flags: -rr script = run after load, keep GUI

## Tool suite location
oss-cad-suite (Yosys 0.70, iverilog, vvp) lives in OpenROAD/oss-cad-suite; ~/Ammar_Linux/oss-cad-suite is a link to it.
Override with ORFS_OSS. Old copy (Yosys 0.62) and its tgz were deleted. or_source.sh (old env script) still works.

## Saved runs (survive clean_all)
Every successful GDSII build is copied to <proj>/out/runs/<id>/ (gds, netlist, sdc, odb/def/spef, reports, inputs/, summary.txt, stack.txt, 3d/); out/latest -> newest; out/runs.tsv = history.
osave | oruns | ocmp [A=2] [B=1] | oshow [-3] [run|latest|N] | oprune [keep=5]     (wizard hub: h = history)
ORFS_SNAP_FULL=0 saves only gds/v/sdc (small). Identical rebuilds are skipped. Sweeps save one run per period.

## v3.3 reliability (content hashes)
_omake checks make's exit code. Each saved run has out/runs/<id>/manifest.json (input_hash, env_hash, tool versions, metrics, timing_met).
out/.stages records the input hash each stage result was built from; ostale [proj] prints fresh|stale|unknown|missing per stage (wizard hub uses it).
osweep reuses a saved run with identical inputs + tool versions (column "source": saved|built) and always restores the SDC.
otest [quick] = self-test on a throwaway project (zz_selftest, deleted afterwards). Rollback: Archive/v33-backup/rollback.sh

## v3.4 odoctor
odoctor [-q] [project ...]  read-only health check (PASS / WARN / FAIL with a fix line): tools and versions, ORFS checkout, platforms,
disk space on / and /home, display/OpenGL, toolkit files and functions, every project (top module, SDC, clk, saved-run timing).
Exit code 1 only on FAIL. otest runs "odoctor --quiet". Source: Tools/odoctor.py. Rollback: Archive/v34-backup/rollback.sh
