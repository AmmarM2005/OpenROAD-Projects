# OpenROAD RTL-to-GDSII toolkit: handover

Base folder: `/home/ammar/Ammar_Linux/OpenROAD`. Shell: zsh. Everything lives under /home.
Commands come from `Tools/orfs-tools.sh` (loaded by your zsh setup). Run `ohelp` for the short list.

## 1. Daily use

| You want to | Command |
|---|---|
| Guided walk, RTL to GDSII | `Chip Designing OPENROAD` |
| New project (starter RTL, testbench, SDC, config) | `onew <name> [sky130hd\|nangate45] [clk_ns]` |
| Simulate | `osim [proj]` |
| Check inputs before a run | `ocheck [proj]` |
| Whole flow, then summary | `orun [proj]` |
| One stage | `osyn` `ofp` `opl` `octs` `ort` `ogds` |
| Summary / which stages exist | `osum` / `ostat` / `ostale` |
| Change clock, rebuild | `operiod <ns>` then `ofresh` |
| Clean / clean and rebuild | `oclean` / `ofresh` (needed after editing config.mk or the SDC) |
| Try several clocks | `osweep [proj] 4.0 3.0 2.0` |
| Open a stage in OpenROAD GUI | `ogui <stage> [proj]` |
| Final layout in KLayout (labels hidden) | `oshow latest [proj] &!` (`OSHOW_ALL=1 oshow ...` shows everything) |
| 2.5D view with metal stack | `oshow -3 latest [proj] &!` or `o3d [proj]` |
| Saved runs: list, compare, prune | `oruns` / `ocmp [A] [B]` / `oprune [keep]` |
| Self-test of the toolkit | `otest quick` |
| Environment check | `odoctor` |

`[proj]` is optional inside a project folder. Run GUI commands with `&!` so the terminal stays free.

## 2. Reading the result

`osum` ends with one verdict line:

- `✓ ALL CLEAR`: timing met and 0 DRC violations.
- `✗ TIMING FAILED`: negative slack. Raise the clock period (`operiod <ns>`), then `ofresh`. ORFS still writes a GDS in this case, so always read the verdict, not just "GDSII done".
- `✗ DRC FAILED`: routing left violations.
- `⚠ TIMING NOT CHECKED` (slack INF): no constrained paths. Usually the SDC clock port is not in the RTL; `ocheck` shows it.
- `⚠ ...`: a result is missing; run the flow.

## 3. When something fails

A failed make prints the first errors, then "what happened / how to fix it" for the known cases:
Verilog syntax error, top module not matching `DESIGN_NAME`, missing file, routing congestion, floorplan/die too small,
SDC port not found, disk full, out of memory. The full log is `<project>/make.log`.
`ocheck` stops obvious problems before the flow starts: missing SDC or RTL, wrong platform, SDC clock port not in the RTL.
A failed or killed run saves nothing; fix the cause and run `orun` again (no clean needed after a kill).

## 4. Project layout

`Projects/<name>/rtl/*.v|*.sv`, `tb/`, `constraint.sdc`, `config.mk` (first line `PROJ_DIR`, repaired automatically),
`make.log`, `out/runs/<id>/` (saved runs with manifest), `out/runs.tsv`, `out/latest`, `3d/`.
Runs are saved automatically when the GDSII is built. Stale detection compares content hashes of RTL, SDC and config.

## 5. Wizard keys

Hub: number = open step, `a` guided walk, `r` run remaining, `s` summary, `f` final layout (OpenROAD), `k` KLayout,
`3d` 2.5D view, `c` change clock, `h` history, `x` clean everything, `q` quit.
Inside a step: `v` view, `l` log, `p` report, `k` KLayout, `3` 2.5D, `r` rebuild to here, `g` guided walk, Enter back.
A key that does not apply prints a short message instead of being ignored.

## 6. Backups and rollback

Every patch saved a copy first in `Archive/encfix/` named `<file>.before-<what>.<timestamp>`. Restore with
`cp -v <backup> <original path>` (the patch prints the exact line). Existing backups:
`before-orunfix2`, `before-verdict`, `before-review`, `before-cleanview`, `before-notext`, `before-inf`.
Deleted test projects are in `Archive/zz-test-projects.*.tar.gz`, `zzfail-gate-d.*.tar.gz`, `zzfail2-gate-d.*.tar.gz`
(`tar -xzf <file> -C Projects` restores them).

## 7. Known limits and rules

- OpenROAD's built-in 3D tab is empty on this build; use KLayout 2.5D.
- Do not copy a zsh function with `functions[new]="$functions[old]"`: it corrupts non-ASCII characters. Use `functions -c old new`.
- Tiny designs use a fixed `DIE_AREA`/`CORE_AREA`; `CORE_UTILIZATION` caused routing loops.
- Large pastes can crash the terminal: run scripts as files (`python3 -I file.py`, `zsh file.zsh`).
- No `apt install`; the root partition is nearly full.

## 7b. Acceptance gates

(a) audit and preserve: done. (b) UTF-8 repair: done. (c) full guided journey: see Section 8. (d) failure and recovery: done
(missing SDC, wrong top, bad clock port, syntax error, killed run, all checked). (e) handover: this file.

## 8. Gate (c) checklist (guided journey)

In a new terminal: `Chip Designing OPENROAD`, new name `adder8`, platform sky130hd. Walk steps 1 to 10 with `a`.
Pass when: every step turns to ✓, the final box shows `✓ ALL CLEAR`, `k` opens a readable KLayout, `3` opens the 2.5D view,
`h` shows the run in history, and `oruns adder8` lists one saved run.

## 9. Where each step writes its files

Every project folder has three shortcuts, `Projects/<name>/results`, `logs` and `reports`. They point to the real ORFS folders
`OpenROAD-flow-scripts/flow/{results,logs,reports}/<platform>/<design>/base/`. Paths below are relative to those shortcuts.

| Step | Command | Result | Logs | Reports |
|---|---|---|---|---|
| Synthesis | `osyn` | `results/1_synth.odb` | `logs/1_2_yosys.log`, `logs/1_1_yosys_canonicalize.log` | `reports/synth_stat.txt` |
| Floorplan | `ofp` | `results/2_floorplan.odb` | `logs/2_1_floorplan.log`, `logs/2_4_floorplan_pdn.log` | `reports/2_floorplan_final.rpt` |
| Placement | `opl` | `results/3_place.odb` | `logs/3_3_place_gp.log`, `logs/3_5_place_dp.log` | `reports/3_detailed_place.rpt`, `reports/3_global_place.rpt`, `reports/3_resizer.rpt` |
| Clock tree | `octs` | `results/4_cts.odb` | `logs/4_1_cts.log` | `reports/4_cts_final.rpt` |
| Routing | `ort` | `results/5_route.odb` | `logs/5_2_route.log`, `logs/5_1_grt.log` | `reports/5_route_drc.rpt`, `reports/5_global_route.rpt` |
| GDSII | `ogds` | `results/6_final.gds` | `logs/6_report.log`, `logs/6_1_merge.log` | `reports/6_finish.rpt` |

Other places:
- `Projects/<name>/make.log`: the full output of the last flow command (first thing to read after a failure).
- `Projects/<name>/out/runs/<id>/`: a saved copy of every finished run: `6_final.gds`, `6_final.v/.def/.spef/.odb`, `summary.txt`, `manifest.json`, `reports/`, `inputs/` (the RTL, SDC and config used), `3d/` (2.5D script).
- `Projects/<name>/out/runs.tsv`: the table behind `oruns`; `out/latest` points at the newest run.
- `Projects/<name>/sim/wave.vcd`: waveform from `osim`.
- `Projects/<name>/out/report.html`: the HTML report (section 10).
- In the wizard, `l` shows a step's log and `p` its report.

## 10. HTML report, Yosys and GitHub

- **HTML report:** `oreport <name>` writes `Projects/<name>/out/report.html` (runs, area, power, timing, charts, saved reports). In the wizard hub press `w`: it builds the report and opens it in the browser.
- **Yosys:** `oyosys [rtl|net] [name]` opens an interactive Yosys shell with the design loaded: `rtl` reads your Verilog, `net` reads the synthesized netlist with the platform library. In the wizard, at the Synthesis step press `y` (RTL) or `n` (netlist); in the hub `y`. Type `exit` to come back. Inside Yosys: `stat`, `ls`, `synth -top <top>`, `abc ...`, `show` (needs graphviz).
- **GitHub:** `opush "message"` commits everything whitelisted in `.gitignore` (Tools, Docs, each project's rtl/tb/SDC/config, saved runs' final GDS, summaries and reports, the HTML report) and pushes to `origin main`. Files over 5 MB stop the push. Use `oprune` to keep the number of saved runs small.
- **Hub marks:** step 10 shows a red cross when timing or DRC failed, and an amber warning when timing was not checked.
