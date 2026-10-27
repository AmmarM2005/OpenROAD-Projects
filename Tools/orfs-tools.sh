# ===== orfs-tools.sh v3 : short commands for the ORFS RTL -> GDSII flow =====
export ORFS_ROOT="${ORFS_ROOT:-$HOME/Ammar_Linux/OpenROAD}"
export ORFS_FLOW="$ORFS_ROOT/OpenROAD-flow-scripts/flow"
export ORFS_PROJECTS="$ORFS_ROOT/Projects"
export ORFS_TOOLS="$ORFS_ROOT/Tools"
export ORFS_TMP="$ORFS_ROOT/Tmp"
export ORFS_OSS="${ORFS_OSS:-$ORFS_ROOT/oss-cad-suite}"
export ORFS_YOSYS="$ORFS_OSS/bin/yosys"
mkdir -p "$ORFS_TMP" "$ORFS_PROJECTS"

# ---- helpers ----
_ofix() {   # keep config.mk valid wherever the project folder lives (mtime preserved)
  local p="$1" c="$1/config.mk" cur ref="$ORFS_TMP/.mtime_ref"
  [[ -f "$c" ]] || return 0
  touch -r "$c" "$ref"
  if ! grep -q '^PROJ_DIR' "$c"; then
    sed -i -E "s|/[^ ()]*/${p:t}/|\$(PROJ_DIR)/|g" "$c"
    sed -i "1i PROJ_DIR = $p" "$c"
  fi
  cur="$(grep -m1 '^PROJ_DIR' "$c" | sed -E 's/^PROJ_DIR *= *//')"
  [[ "$cur" == "$p" ]] || sed -i -E "s|^PROJ_DIR *=.*|PROJ_DIR = $p|" "$c"
  touch -r "$ref" "$c"
}
_oproj() {   # project dir from a name, or by walking up from the current dir
  local d
  if [[ -n "$1" ]]; then d="$ORFS_PROJECTS/$1"
  else
    d="$PWD"
    while [[ "$d" != "/" && ! -f "$d/config.mk" ]]; do d="$(dirname "$d")"; done
  fi
  if [[ ! -f "$d/config.mk" ]]; then echo "no project found: give a name, or cd into a project" >&2; return 1; fi
  _ofix "$d"
  echo "$d"
}
_ovar()  { grep -E "^export $2[[:space:]]*=" "$1/config.mk" | head -1 | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]]+$//'; }
_oname() { local n; n="$(_ovar "$1" DESIGN_NICKNAME)"; [[ -z "$n" ]] && n="$(_ovar "$1" DESIGN_NAME)"; echo "$n"; }
_olink() {   # convenience links: <project>/results, logs, reports
  local p="$1" name plat d
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  for d in results logs reports; do ln -sfn "$ORFS_FLOW/$d/$plat/$name/base" "$p/$d"; done
}
_oexplain() {   # _oexplain <make.log> : plain-English hints for common failures (prints nothing when nothing matches)
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
  local p="$1"; shift
  local log="$p/make.log"
  mkdir -p "$ORFS_TMP"
  ( cd "$ORFS_FLOW" && env YOSYS_EXE="$ORFS_YOSYS" OPENROAD_EXE=/usr/bin/openroad TMPDIR="$ORFS_TMP" \
      make DESIGN_CONFIG="$p/config.mk" LEC_CHECK=0 "$@" ) > "$log" 2>&1
  local rc=$?
  if (( rc != 0 )) || grep -q -E "^make(\[[0-9]+\])?: \*\*\*" "$log"; then
    echo "✗ FAILED (make exit code $rc). First errors (full log: $log):"
    grep -n -i -E "error|\*\*\*" "$log" | head -8
    _oexplain "$log"
    return 1
  fi
}
_ostage() {  # _ostage <result file> <label> <project name>
  local file="$1" label="$2" p name plat t0=$SECONDS
  p="$(_oproj "$3")" || return 1
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  echo "▶ $label  [$name / $plat]"
  _olink "$p"
  _omake "$p" "results/$plat/$name/base/$file" || return 1
  echo "✓ $label done ($((SECONDS - t0))s)"
}
_ometrics() {  # sets SLACK POWER AREA UTIL DRC CTSINFO
  local p="$1" name plat lg rep s b
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  lg="$ORFS_FLOW/logs/$plat/$name/base"; rep="$ORFS_FLOW/reports/$plat/$name/base/6_finish.rpt"
  SLACK="$(grep -h "worst slack max" "$rep" 2>/dev/null | head -1 | awk '{print $4}')"
  POWER="$(grep -h "Total power" "$lg/6_report.log" 2>/dev/null | head -1 | awk '{printf "%.3f", $4*1000}')"
  AREA="$(grep -h "Design area" "$lg/6_report.log" 2>/dev/null | head -1 | awk '{print $3}')"
  UTIL="$(grep -h "Design area" "$lg/6_report.log" 2>/dev/null | head -1 | awk '{print $5}')"
  DRC="$(grep -h "Number of violations" "$lg/5_2_route.log" 2>/dev/null | tail -1 | awk '{print $NF}' | tr -d '.')"
  s="$(grep -h "CTS-0010" "$lg/4_1_cts.log" 2>/dev/null | head -1 | sed -nE 's/.*has ([0-9]+) sinks.*/\1/p')"
  b="$(grep -h "CTS-0018" "$lg/4_1_cts.log" 2>/dev/null | head -1 | sed -nE 's/.*Created ([0-9]+) clock buffers.*/\1/p')"
  CTSINFO=""; [[ -n "$s" ]] && CTSINFO="$s sinks, $b clock buffers"
}
_ocfg_write() {  # _ocfg_write <projdir> <name> <platform>
  cat > "$1/config.mk" <<__CFG__
# Project location (kept up to date automatically by the toolkit)
PROJ_DIR = $1

# Only a few lines ever change between designs.
# DESIGN_NAME must equal the top module name in your RTL.
export DESIGN_NICKNAME = $2
export DESIGN_NAME     = $2
export PLATFORM        = $3

export VERILOG_FILES = \$(sort \$(wildcard \$(PROJ_DIR)/rtl/*.v) \$(wildcard \$(PROJ_DIR)/rtl/*.sv))
export SDC_FILE      = \$(PROJ_DIR)/constraint.sdc

# Die size, pick ONE option. Option A: fixed die in um (good for tiny designs).
export DIE_AREA  = 0 0 120 120
export CORE_AREA = 10 10 110 110
# Option B (bigger designs, e.g. a CPU): comment out the two lines above, uncomment:
# export CORE_UTILIZATION = 30

export PLACE_DENSITY_LB_ADDON = 0.20
__CFG__
}

# ---- create a project ----
onew() {   # onew <name> [platform=sky130hd] [clk_ns=5.0]
  local name="$1" plat="${2:-sky130hd}" clk="${3:-5.0}"
  if [[ -z "$name" ]]; then echo "usage: onew <name> [platform=sky130hd] [clk_ns=5.0]"; return 1; fi
  [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "name must be a valid Verilog identifier"; return 1; }
  if [[ ! -d "$ORFS_FLOW/platforms/$plat" ]]; then echo "unknown platform '$plat'. Available:"; ls "$ORFS_FLOW/platforms"; return 1; fi
  local p="$ORFS_PROJECTS/$name"
  if [[ -e "$p" ]]; then echo "$p already exists"; return 1; fi
  mkdir -p "$p/rtl" "$p/tb"

  cat > "$p/rtl/$name.v" <<'__V__'
// Starter design (a registered 8-bit adder). Replace with your own RTL.
// The top module name must match DESIGN_NAME in config.mk.
module @NAME@ (
    input  wire       clk,
    input  wire [7:0] a,
    input  wire [7:0] b,
    output reg  [8:0] sum
);
    always @(posedge clk) sum <= {1'b0, a} + {1'b0, b};
endmodule
__V__

  cat > "$p/tb/tb_$name.v" <<'__TB__'
`timescale 1ns/1ps
module tb_@NAME@;
    reg clk = 0;
    reg [7:0] a, b;
    wire [8:0] sum;
    integer i, errors;
    @NAME@ dut (.clk(clk), .a(a), .b(b), .sum(sum));
    always #5 clk = ~clk;
    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, tb_@NAME@);
        errors = 0;
        for (i = 0; i < 40; i = i + 1) begin
            a = i * 7; b = i * 13 + 1;
            @(posedge clk); #1;
            if (sum !== ({1'b0, a} + {1'b0, b})) begin
                errors = errors + 1;
                $display("FAIL a=%0d b=%0d sum=%0d", a, b, sum);
            end
        end
        if (errors == 0) $display("PASS");
        else $display("FAILED: %0d errors", errors);
        $finish;
    end
endmodule
__TB__

  cat > "$p/constraint.sdc" <<'__SDC__'
set clk_period @CLK@
set io_delay [expr {$clk_period * 0.2}]
create_clock -name core_clock -period $clk_period [get_ports clk]
set_input_delay  $io_delay -clock core_clock [delete_from_list [all_inputs] [get_ports clk]]
set_output_delay $io_delay -clock core_clock [all_outputs]
__SDC__

  sed -i "s|@NAME@|$name|g; s|@CLK@|$clk|g" "$p/rtl/$name.v" "$p/tb/tb_$name.v" "$p/constraint.sdc"
  _ocfg_write "$p" "$name" "$plat"
  _olink "$p"
  echo "✓ created $p"
  echo "  edit: rtl/$name.v  tb/tb_$name.v  constraint.sdc  (config.mk only for die size / platform)"
}

# ---- flow stages (each runs everything before it that isn't done yet) ----
osyn()  { _ostage 1_synth.odb     "synthesis"  "$1"; }
ofp()   { _ostage 2_floorplan.odb "floorplan"  "$1"; }
opl()   { _ostage 3_place.odb     "placement"  "$1"; }
octs()  { _ostage 4_cts.odb       "clock tree" "$1"; }
ort()   { _ostage 5_route.odb     "routing"    "$1"; }
ogds()  { _ostage 6_final.gds     "GDSII"      "$1"; }
orun()  { ogds "$@" && osum "$@"; }                 # full flow + summary
oclean(){ local p; p="$(_oproj "$1")" || return 1; _omake "$p" clean_all && echo "✓ cleaned"; }
ofresh(){ oclean "$@" && orun "$@"; }               # use after editing config.mk or the SDC

# ---- results ----
osum() {
  local p name plat gds
  p="$(_oproj "$1")" || return 1
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  _ometrics "$p"
  gds="$ORFS_FLOW/results/$plat/$name/base/6_final.gds"
  echo "── $name ($plat) ──────────────────────────"
  if [[ -f "$gds" ]]; then echo "GDSII       : $gds"; else echo "GDSII       : not built yet (run: ogds)"; fi
  echo "area        : ${AREA:-?} um^2  (${UTIL:-?} utilization)"
  echo "power       : ${POWER:-?} mW"
  echo "setup slack : ${SLACK:-?} ns"
  echo "DRC         : ${DRC:-?} violations"
  echo "clock tree  : ${CTSINFO:-none}"
  local rep="$ORFS_FLOW/reports/$plat/$name/base/6_finish.rpt" wns tns clk
  wns="$(grep -h -m1 -E '^wns max' "$rep" 2>/dev/null | awk '{print $3}')"
  tns="$(grep -h -m1 -E '^tns max' "$rep" 2>/dev/null | awk '{print $3}')"
  clk="$(grep -E '^set clk_period' "$p/constraint.sdc" 2>/dev/null | head -1 | awk '{print $3}')"
  [[ -n "$wns" ]] && echo "WNS / TNS   : $wns / ${tns:-?} ns"
  echo
  if [[ -z "$SLACK" ]]; then
    echo "⚠ NO TIMING RESULT YET (run: ogds)"
  elif [[ ! "$SLACK" =~ '^-?[0-9]+(\.[0-9]+)?$' ]]; then
    echo "⚠ TIMING NOT CHECKED: slack is '$SLACK' (no constrained paths). Does the clock port in constraint.sdc exist in the RTL? (ocheck)"
  elif awk -v s="$SLACK" 'BEGIN{exit !(s<0)}'; then
    echo "✗ TIMING FAILED: slack $SLACK ns at ${clk:-?} ns. Raise clk_period (operiod <ns>), then ofresh"
  elif [[ -z "$DRC" ]]; then
    echo "⚠ TIMING MET (slack $SLACK ns), but the DRC count was not found in the routing log"
  elif [[ "$DRC" != "0" ]]; then
    echo "✗ DRC FAILED: $DRC violations in routing (timing met)"
  else
    echo "✓ ALL CLEAR: timing met (slack $SLACK ns), 0 DRC violations"
  fi
}
ostat() {   # which stages have results
  local p name plat d f
  p="$(_oproj "$1")" || return 1
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  d="$ORFS_FLOW/results/$plat/$name/base"
  for f in 1_synth.odb 2_floorplan.odb 3_place.odb 4_cts.odb 5_route.odb 6_final.gds; do
    if [[ -f "$d/$f" ]]; then echo "  ✓ $f"; else echo "  · $f"; fi
  done
}

# ---- GUI: open any stage ----
_oview() {   # plain viewer for any .odb (layout only, no timing data loaded)
  local t="$ORFS_TMP/view.tcl"
  mkdir -p "$ORFS_TMP"; echo "read_db $1" > "$t"
  QT_QPA_PLATFORM=xcb /usr/bin/openroad -gui "$t"
}
ogui() {   # ogui <stage> [project]   (stage list: ogui help)
  local st="${1:-final}" f full=0 pn p name plat odb
  case "$st" in
    help|-h) cat <<'__GH__'
 stage          what you see                                   (timing tabs?)
 synth          netlist as a placed-at-origin database          no
 floorplan, fp  die, core, rows, IO pins, power grid            yes
 tap            rows + tap cells (before the power grid)        no
 pdn            + power grid straps                             no
 gp             global placement (cells spread, overlapping)    no
 place, pl      detailed placement (legal, final cell spots)    yes
 cts            + clock tree buffers                            yes
 groute, grt    global routing                                  no
 route, rt      detailed routing (all wires)                    yes
 final          + fill cells, parasitics                        yes
 Anything ending in .odb also works, e.g. 3_2_place_iop.odb
__GH__
      return 0;;
    synth)         f=1_synth.odb ;;
    floorplan|fp)  f=2_floorplan.odb; full=1; st=floorplan ;;
    tap)           f=2_3_floorplan_tapcell.odb ;;
    pdn)           f=2_4_floorplan_pdn.odb ;;
    gp)            f=3_3_place_gp.odb ;;
    place|pl)      f=3_place.odb; full=1; st=place ;;
    cts)           f=4_cts.odb; full=1 ;;
    groute|grt)    f=5_1_grt.odb ;;
    route|rt)      f=5_route.odb; full=1; st=route ;;
    final)         f=6_final.odb; full=1 ;;
    *.odb)         f="$st" ;;
    *) echo "unknown stage '$st'. Try: ogui help"; return 1 ;;
  esac
  shift; pn="$1"
  p="$(_oproj "$pn")" || return 1
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  _ostage "$f" "building up to $st" "$pn" || return 1
  odb="$ORFS_FLOW/results/$plat/$name/base/$f"
  echo "▶ opening $f"
  if [[ $full -eq 1 ]]; then
    ( cd "$ORFS_FLOW" && env YOSYS_EXE="$ORFS_YOSYS" OPENROAD_EXE=/usr/bin/openroad TMPDIR="$ORFS_TMP" \
        QT_QPA_PLATFORM=xcb make DESIGN_CONFIG="$p/config.mk" LEC_CHECK=0 "gui_$st" ) \
      || { echo "(ORFS viewer failed, opening plain viewer)"; _oview "$odb"; }
  else
    _oview "$odb"
  fi
}
o3d() {    # KLayout 2.5d view of the final GDS
  local p name plat gds s
  p="$(_oproj "$1")" || return 1
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  gds="$ORFS_FLOW/results/$plat/$name/base/6_final.gds"
  if [[ ! -f "$gds" ]]; then echo "no GDS yet. Run: ogds"; return 1; fi
  s="$ORFS_TOOLS/25d/$plat.rb"
  if [[ -f "$s" ]]; then
    if command -v xclip >/dev/null 2>&1; then xclip -selection clipboard < "$s" && echo "2.5d script copied to clipboard"
    elif command -v wl-copy >/dev/null 2>&1; then wl-copy < "$s" && echo "2.5d script copied to clipboard"
    else echo "2.5d script is at: $s (open it, copy it)"; fi
    echo "In KLayout: double-click the top cell, press F, Tools > 2.5d View > New 2.5d Script, paste, Run"
  else echo "no 2.5d script for platform '$plat' yet (expected $s)"; fi
  QT_QPA_PLATFORM=xcb klayout "$gds"
}
osim() {   # RTL simulation with iverilog (rtl/*.v + tb/*.v), waves in <project>/sim/wave.vcd
  local p f files=()
  p="$(_oproj "$1")" || return 1
  mkdir -p "$p/sim"
  while IFS= read -r f; do files+=("$f"); done < <(find "$p/rtl" "$p/tb" \( -name '*.v' -o -name '*.sv' \) | sort)
  ( cd "$p/sim" && "$ORFS_OSS/bin/iverilog" -g2012 -o sim.vvp "${files[@]}" \
      && "$ORFS_OSS/bin/vvp" sim.vvp | grep -v "^VCD" | tail -n 15 )
}

# ---- clock-period tools ----
operiod() {   # operiod <ns> [project]  (then run ofresh)
  local per="$1" p
  p="$(_oproj "$2")" || return 1
  sed -i -E "s/^set clk_period .*/set clk_period $per/" "$p/constraint.sdc" && echo "clk_period = $per ns"
}

# ---- navigation / help ----
ols() { ls "$ORFS_PROJECTS"; }
ocd() { cd "$ORFS_PROJECTS/$1" || return 1; }
ohelp() { cat <<'__HELP__'
 Chip Designing OPENROAD    guided wizard + hub to jump to any step
 onew <name> [plat] [clk]   new project (rtl/ tb/ constraint.sdc config.mk), default sky130hd, 5.0 ns
 osim [proj]                simulate rtl/ + tb/ with iverilog
 osyn ofp opl octs ort ogds each stage (runs earlier stages if needed)
 orun [proj]                full flow RTL -> GDSII, then summary
 osum / ostat [proj]        summary / which stages have results
 ogui <stage> [proj]        OpenROAD GUI for any stage (ogui help lists them)
 o3d  [proj]                KLayout 2.5d view of the GDS (script copied to clipboard)
 operiod <ns> [proj]        change clock period, then run ofresh
 osweep [proj] 4.0 3.0 2.0  full flow at several periods, table in sweep.txt
 oclean / ofresh [proj]     clean / clean + full run (needed after editing config.mk or the SDC)
 ols / ocd <name>           list projects / cd into one
 [proj] is optional when you are inside the project folder. Log: <project>/make.log
__HELP__
}

# ---- Chip Designing OPENROAD : guided wizard ----
Chip() {
  if [[ "${(L)1}" == "designing" && "${(L)2}" == "openroad" ]]; then
    python3 "$ORFS_TOOLS/wizard/chipwiz.py" "${@:3}"
  else
    echo "Did you mean:  Chip Designing OPENROAD"
  fi
}
chip() { Chip "$@"; }

# ---- v3.1: KLayout 2D and 2.5D view, stack generated from tech LEF + GDS ----
_okl_run() {   # KLayout (plain 2D view) with text objects hidden unless OSHOW_ALL=1
  local -a nt
  [[ -z "${OSHOW_ALL:-}" ]] && nt=(-rm "$ORFS_TOOLS/notext.rb")
  QT_QPA_PLATFORM=xcb klayout "$@" "${nt[@]}"
}
_oclean_lyp() {   # _oclean_lyp <platform.lyp> : echo a cleaned copy (labels/pins/boundaries hidden); the original if OSHOW_ALL=1 or on any problem
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
  KL_P="$(_oproj "$1")" || return 1
  KL_NAME="$(_oname "$KL_P")"; KL_PLAT="$(_ovar "$KL_P" PLATFORM)"
  KL_GDS="$ORFS_FLOW/results/$KL_PLAT/$KL_NAME/base/6_final.gds"
  local -a lyps; lyps=("$ORFS_FLOW/platforms/$KL_PLAT"/*.lyp(N)); KL_LYP="$(_oclean_lyp "${lyps[1]:-}")"
  if [[ ! -f "$KL_GDS" ]]; then echo "no GDSII yet. Run: ogds"; return 1; fi
}
o3dgen() {   # build <project>/3d/view25d.lyd25 from the platform's thickness data
  _okl_common "$1" || return 1
  mkdir -p "$KL_P/3d"
  python3 "$ORFS_TOOLS/25d/gen25d.py" --platform "$KL_PLAT" --flow "$ORFS_FLOW" --gds "$KL_GDS" \
      --out "$KL_P/3d" --klayout "$(command -v klayout)" --fallback "$ORFS_TOOLS/25d/$KL_PLAT.rb"
}
o3d() {      # KLayout with the 2.5D view already running
  o3dgen "$1" || return 1
  local -a args; args=("$KL_GDS"); [[ -n "$KL_LYP" ]] && args+=(-l "$KL_LYP")
  if command -v xclip >/dev/null 2>&1; then xclip -selection clipboard < "$KL_P/3d/view25d.rb"
  elif command -v wl-copy >/dev/null 2>&1; then wl-copy < "$KL_P/3d/view25d.rb"; fi
  echo "▶ opening KLayout with the 2.5D view"
  echo "  if the 2.5D window does not appear: Tools > 2.5d View > New 2.5d Script, paste ${KL_P}/3d/view25d.rb, Run"
  QT_QPA_PLATFORM=xcb klayout "${args[@]}" -rr "$KL_P/3d/view25d.lyd25"
}
okl() {      # plain KLayout, with the platform's layer colours
  _okl_common "$1" || return 1
  local -a args; args=("$KL_GDS"); [[ -n "$KL_LYP" ]] && args+=(-l "$KL_LYP")
  _okl_run "${args[@]}"
}

# ---- v3.2: saved runs (snapshots that survive clean_all) ----
_osnap() {   # snapshot finished flow results into <project>/out/runs/<id>/ (never fails the flow)
  local p="$1" name plat res rep gm clk id run last f
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  res="$ORFS_FLOW/results/$plat/$name/base"; rep="$ORFS_FLOW/reports/$plat/$name/base"
  [[ -f "$res/6_final.gds" ]] || return 0
  gm="$(stat -c %Y "$res/6_final.gds")"
  mkdir -p "$p/out/runs"
  last="$(readlink "$p/out/latest" 2>/dev/null)"
  if [[ -n "$last" && -f "$p/out/$last/.meta" ]] && grep -q "^gds_mtime=$gm$" "$p/out/$last/.meta"; then return 0; fi
  clk="$(grep -E '^set clk_period' "$p/constraint.sdc" 2>/dev/null | head -1 | awk '{print $3}')"
  id="$(date +%Y%m%d-%H%M%S)_${clk:-x}ns"
  run="$p/out/runs/$id"; mkdir -p "$run/inputs" "$run/reports"
  local -a want; want=(6_final.gds 6_final.v 6_final.sdc)
  [[ "${ORFS_SNAP_FULL:-1}" == 1 ]] && want+=(6_final.odb 6_final.def 6_final.spef)
  for f in $want; do [[ -f "$res/$f" ]] && cp "$res/$f" "$run/"; done
  for f in 6_finish.rpt synth_stat.txt 5_route_drc.rpt 4_cts_final.rpt 3_detailed_place.rpt; do
    [[ -f "$rep/$f" ]] && cp "$rep/$f" "$run/reports/"
  done
  cp -r "$p/rtl" "$run/inputs/" 2>/dev/null
  cp "$p/constraint.sdc" "$p/config.mk" "$run/inputs/" 2>/dev/null
  _ometrics "$p"
  _osum_base "${p:t}" > "$run/summary.txt" 2>&1
  python3 "$ORFS_TOOLS/25d/gen25d.py" --platform "$plat" --flow "$ORFS_FLOW" --gds "$run/6_final.gds" \
      --out "$run/3d" --klayout "$(command -v klayout)" --fallback "$ORFS_TOOLS/25d/$plat.rb" > "$run/stack.txt" 2>&1
  printf "gds_mtime=%s\nclk_ns=%s\nplatform=%s\n" "$gm" "${clk:-?}" "$plat" > "$run/.meta"
  [[ -s "$p/out/runs.tsv" ]] || printf "id\tclk_ns\tslack_ns\tpower_mW\tarea_um2\tutil\tdrc\tclock_tree\n" > "$p/out/runs.tsv"
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$id" "${clk:-?}" "${SLACK:-?}" "${POWER:-?}" "${AREA:-?}" "${UTIL:-?}" "${DRC:-?}" "${CTSINFO:--}" >> "$p/out/runs.tsv"
  ln -sfn "runs/$id" "$p/out/latest"
  return 0
}
# hook: every successful build of 6_final.gds saves a run
functions -c _omake _omake_base
_omake() {
  _omake_base "$@" || return $?
  local p="$1"; shift
  case " $* " in *6_final.gds*) _osnap "$p" ;; esac
  return 0
}
# hook: summary mentions the saved run
functions -c osum _osum_base
osum() {
  _osum_base "$@"
  local p l; p="$(_oproj "$1")" || return 0
  if [[ -L "$p/out/latest" ]]; then l="$(readlink "$p/out/latest")"; echo "saved run   : ${l:t}   (out/latest)"; fi
}
osave() {    # osave [project] : snapshot the current flow results now
  local p before after; p="$(_oproj "$1")" || return 1
  before="$(readlink "$p/out/latest" 2>/dev/null)"
  _osnap "$p"
  after="$(readlink "$p/out/latest" 2>/dev/null)"
  if [[ -z "$after" ]]; then echo "${p:t}: no finished GDSII to save"
  elif [[ "$before" == "$after" ]]; then echo "${p:t}: already saved (${after:t})"
  else echo "${p:t}: saved ${after:t}"; fi
}
_orun_dir() {   # _orun_dir <projdir> <selector>  -> prints the run folder
  local p="$1" sel="${2:-latest}" id=""
  [[ -s "$p/out/runs.tsv" ]] || { echo "no saved runs yet" >&2; return 1; }
  if [[ "$sel" == latest ]]; then
    id="$(readlink "$p/out/latest" 2>/dev/null)"; id="${id:t}"
  elif [[ "$sel" == <-> ]]; then
    id="$(tail -n +2 "$p/out/runs.tsv" | tac | sed -n "${sel}p" | cut -f1)"
  else
    local -a m; m=("$p/out/runs/$sel"*(N/))
    (( ${#m} == 1 )) && id="${m[1]:t}"
  fi
  if [[ -n "$id" && -d "$p/out/runs/$id" ]]; then echo "$p/out/runs/$id"; else echo "no such run: $sel (see: oruns)" >&2; return 1; fi
}
oruns() {    # oruns [project] : history of saved runs, newest first
  local p latest; p="$(_oproj "$1")" || return 1
  [[ -s "$p/out/runs.tsv" ]] || { echo "no saved runs yet (they are saved automatically when the GDSII is built)"; return 0; }
  latest="$(readlink "$p/out/latest" 2>/dev/null)"; latest="${latest:t}"
  awk -F'\t' -v L="$latest" '
    NR==1 { next }
    { id[NR]=$1; clk[NR]=$2; sl[NR]=$3; pw[NR]=$4; ar[NR]=$5; dr[NR]=$7; ct[NR]=$8 }
    END {
      printf "   %-3s %-24s %-7s %-9s %-9s %-9s %-4s %s\n", "#", "run", "clk_ns", "slack_ns", "power_mW", "area_um2", "DRC", "clock tree"
      n = 0
      for (i = NR; i >= 2; i--) {
        n++
        mark = (id[i] == L) ? "*" : " "
        flag = (sl[i] + 0 < 0) ? "  ✗ timing" : ""
        printf " %s %-3d %-24s %-7s %-9s %-9s %-9s %-4s %s%s\n", mark, n, id[i], clk[i], sl[i], pw[i], ar[i], dr[i], ct[i], flag
      }
    }' "$p/out/runs.tsv"
}
ocmp() {     # ocmp [A=2] [B=1] [project] : compare two saved runs (numbers from oruns, or ids)
  local p da db dd; p="$(_oproj "$3")" || return 1
  da="$(_orun_dir "$p" "${1:-2}")" || return 1
  db="$(_orun_dir "$p" "${2:-1}")" || return 1
  awk -F'\t' -v A="${da:t}" -v B="${db:t}" '
    NR==1 { for (i=1;i<=NF;i++) h[i]=$i; next }
    $1==A { for (i=1;i<=NF;i++) a[i]=$i }
    $1==B { for (i=1;i<=NF;i++) b[i]=$i }
    END {
      printf "  %-10s %-24s %-24s %s\n", "", "A", "B", "change (B - A)"
      printf "  %-10s %-24s %-24s\n", "run", A, B
      for (i=2;i<=7;i++) {
        d = ""
        if (a[i] ~ /^-?[0-9.]+$/ && b[i] ~ /^-?[0-9.]+$/) d = sprintf("%+.3f", b[i]-a[i])
        printf "  %-10s %-24s %-24s %s\n", h[i], a[i], b[i], d
      }
    }' "$p/out/runs.tsv"
  echo; echo "  what changed in the inputs (A -> B):"
  dd="$(diff -ru "$da/inputs" "$db/inputs")"
  if [[ -z "$dd" ]]; then echo "    identical inputs"; else echo "$dd" | head -60; fi
}
oshow() {    # oshow [-3] [run|latest|N] [project] : open a saved run in KLayout (-3 = 2.5D view)
  local d3=0; [[ "$1" == "-3" ]] && { d3=1; shift; }
  local p run plat; p="$(_oproj "$2")" || return 1
  run="$(_orun_dir "$p" "${1:-latest}")" || return 1
  plat="$(_ovar "$p" PLATFORM)"
  local -a lyps args; lyps=("$ORFS_FLOW/platforms/$plat"/*.lyp(N)); args=("$run/6_final.gds")
  [[ -n "${lyps[1]:-}" ]] && args+=(-l "$(_oclean_lyp "${lyps[1]}")")
  echo "▶ ${run:t}${OSHOW_ALL:+  (all layers)}"
  if (( d3 )); then
    [[ -f "$run/3d/view25d.lyd25" ]] || { echo "this run has no 2.5D script, see ${run}/stack.txt"; return 1; }
    QT_QPA_PLATFORM=xcb klayout "${args[@]}" -rr "$run/3d/view25d.lyd25"
  else
    _okl_run "${args[@]}"
  fi
}
oprune() {   # oprune [keep=5] [project] : delete all but the newest N saved runs
  local keep="${1:-5}" p n=0 id
  [[ "$keep" == <-> ]] || { echo "usage: oprune [how-many-to-keep] [project]"; return 1; }
  p="$(_oproj "$2")" || return 1
  [[ -s "$p/out/runs.tsv" ]] || { echo "no saved runs"; return 0; }
  local -a ids old; ids=("${(@f)$(tail -n +2 "$p/out/runs.tsv" | tac | cut -f1)}")
  for id in $ids; do n=$((n+1)); (( n > keep )) && old+=("$id"); done
  (( ${#old} )) || { echo "nothing to prune (${#ids} runs, keeping $keep)"; return 0; }
  echo "will delete ${#old} run(s): ${old[*]}"
  read -q "REPLY?Delete them? (y/N) " || { echo; echo "cancelled"; return 0; }
  echo
  for id in $old; do rm -rf "$p/out/runs/$id"; sed -i "/^${id}\t/d" "$p/out/runs.tsv"; done
  echo "done"
}

# ---- v3.3: reliability (content hashes, manifests, stage records, sweep reuse, self-test) ----
_ojq() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
_ojget() {   # _ojget <manifest.json> <key> : value of a simple "key": value line
  sed -n 's/^ *"'"$2"'": *"\{0,1\}\([^",]*\)"\{0,1\},\{0,1\} *$/\1/p' "$1" | head -1
}
_ohash() {   # recursive RTL/header + SDC/config content hash
  python3 "$ORFS_TOOLS/ohash.py" "$1"
}
_oenv() {    # sets tool versions and a fingerprint of the ORFS checkout
  local dirty
  OENV_OPENROAD="$(/usr/bin/openroad -version 2>/dev/null | head -1 | tr -d '\r')"
  OENV_YOSYS="$("$ORFS_YOSYS" -V 2>/dev/null | head -1)"
  OENV_ORFS="$(git -C "$ORFS_FLOW" rev-parse --short HEAD 2>/dev/null)"

  # Include tracked changes and checksums of non-ignored untracked files.
  # Generated files ignored by Git do not affect the fingerprint.
  dirty="$(
    {
      git -C "$ORFS_FLOW" diff --binary HEAD -- 2>/dev/null
      git -C "$ORFS_FLOW" ls-files --others --exclude-standard -z 2>/dev/null |
        xargs -0 -r sha256sum 2>/dev/null
    } | sha256sum | cut -c1-12
  )"
  OENV_DIRTY="$dirty"
  OENV_KLAYOUT="$(klayout -v 2>/dev/null | head -1)"
  OENV_ID="$(printf '%s|%s|%s|%s|%s' \
    "$OENV_OPENROAD" "$OENV_YOSYS" "$OENV_KLAYOUT" \
    "$OENV_ORFS" "$OENV_DIRTY" | sha256sum | cut -c1-12)"
}

# stage records: which input hash each stage result was built from
_ostage_files=(1_synth.odb 2_floorplan.odb 3_place.odb 4_cts.odb 5_route.odb 6_final.gds)
_ostage_mtimes() {   # "file mtime" for each existing stage result
  local p="$1" name plat d f
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"; d="$ORFS_FLOW/results/$plat/$name/base"
  for f in $_ostage_files; do [[ -f "$d/$f" ]] && echo "$f $(stat -c %Y "$d/$f")"; done
}
_orecord_stages() {  # _orecord_stages <projdir> "<mtimes before the build>"
  local p="$1" before="$2" cur f m rec="$1/out/.stages"
  cur="$(_ohash "$p")"
  mkdir -p "$p/out"; touch "$rec"
  _ostage_mtimes "$p" | while read -r f m; do
    if ! print -r -- "$before" | grep -q "^$f $m$"; then
      grep -v "^$f " "$rec" > "$rec.tmp" 2>/dev/null
      echo "$f $m $cur" >> "$rec.tmp"; mv "$rec.tmp" "$rec"
    fi
  done
}
functions -c _omake _omake_v32
_omake() {
  local p="$1" pre rc
  pre="$(_ostage_mtimes "$p" 2>/dev/null)"
  _omake_v32 "$@"; rc=$?
  (( rc == 0 )) && _orecord_stages "$p" "$pre"
  return $rc
}
ostale() {   # ostale [proj] : per stage result: fresh | stale | unknown | missing (by content hash)
  local p name plat d f cur rec fm rmt rh
  p="$(_oproj "$1")" || return 1
  name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"; d="$ORFS_FLOW/results/$plat/$name/base"
  cur="$(_ohash "$p")"
  for f in $_ostage_files; do
    if [[ ! -f "$d/$f" ]]; then echo "$f missing"; continue; fi
    fm="$(stat -c %Y "$d/$f")"
    rec="$(grep -m1 "^$f " "$p/out/.stages" 2>/dev/null)"
    if [[ -n "$rec" ]]; then
      rmt="$(print -r -- "$rec" | awk '{print $2}')"; rh="$(print -r -- "$rec" | awk '{print $3}')"
      if [[ "$rmt" == "$fm" ]]; then
        if [[ "$rh" == "$cur" ]]; then echo "$f fresh"; else echo "$f stale"; fi
        continue
      fi
    fi
    echo "$f unknown"
  done
}

# run manifests
_oman_write() {   # _oman_write <run dir> <projdir>
  local run="$1" p="$2" id name plat clk ih met f
  local -a fl
  id="${run:t}"; name="$(_oname "$p")"; plat="$(_ovar "$p" PLATFORM)"
  clk="$(grep -E '^set clk_period' "$run/inputs/constraint.sdc" 2>/dev/null | head -1 | awk '{print $3}')"
  ih="$(_ohash "$run/inputs")"
  _oenv; _ometrics "$p"
  met=null
  if [[ -n "$SLACK" ]]; then
    if awk -v s="$SLACK" 'BEGIN{exit !(s<0)}'; then met=false; else met=true; fi
  fi
  for f in "$run"/inputs/rtl/*(N.); do fl+=("    \"rtl/${f:t}\": \"$(sha256sum "$f" | cut -c1-12)\""); done
  for f in constraint.sdc config.mk; do
    [[ -f "$run/inputs/$f" ]] && fl+=("    \"$f\": \"$(grep -v '^PROJ_DIR' "$run/inputs/$f" | sha256sum | cut -c1-12)\"")
  done
  {
    echo "{"
    echo "  \"schema\": 1,"
    echo "  \"id\": \"$id\","
    echo "  \"created\": \"$(date -Is)\","
    echo "  \"design\": \"$name\","
    echo "  \"platform\": \"$plat\","
    echo "  \"clk_ns\": \"${clk:-unknown}\","
    echo "  \"input_hash\": \"$ih\","
    echo "  \"env_hash\": \"$OENV_ID\","
    echo "  \"openroad\": \"$(_ojq "$OENV_OPENROAD")\","
    echo "  \"yosys\": \"$(_ojq "$OENV_YOSYS")\","
    echo "  \"klayout\": \"$(_ojq "$OENV_KLAYOUT")\","
    echo "  \"orfs_commit\": \"${OENV_ORFS:-unknown}\","
    echo "  \"slack_ns\": \"${SLACK:-unknown}\","
    echo "  \"power_mW\": \"${POWER:-unknown}\","
    echo "  \"area_um2\": \"${AREA:-unknown}\","
    echo "  \"util\": \"${UTIL:-unknown}\","
    echo "  \"drc\": \"${DRC:-unknown}\","
    echo "  \"clock_tree\": \"$(_ojq "${CTSINFO:--}")\","
    echo "  \"timing_met\": $met,"
    echo "  \"files\": {"
    print -r -- "${(pj:,\n:)fl}"
    echo "  }"
    echo "}"
  } > "$run/manifest.json"
}
functions -c _osnap _osnap_v32
_osnap() {
  local p="$1" before after
  before="$(readlink "$p/out/latest" 2>/dev/null)"
  _osnap_v32 "$p"
  after="$(readlink "$p/out/latest" 2>/dev/null)"
  [[ -n "$after" && "$after" != "$before" ]] && _oman_write "$p/out/$after" "$p"
  return 0
}

# sweep that reuses saved runs with identical inputs and tools
_ofind_run() {   # _ofind_run <projdir> <input_hash> <env_id> : prints the newest matching run dir
  local p="$1" ih="$2" ev="$3" m
  local -a ms; ms=("$p"/out/runs/*/manifest.json(N))
  for m in ${(Oa)ms}; do
    if [[ "$(_ojget "$m" input_hash)" == "$ih" && "$(_ojget "$m" env_hash)" == "$ev" ]]; then echo "${m:h}"; return 0; fi
  done
  return 1
}
osweep() {    # osweep [project] <p1> <p2> ... : full flow per clock period; identical saved runs are reused
  local proj="" p orig per ih ev run sdc_bak
  if [[ ! "$1" =~ ^[0-9.]+$ ]]; then proj="$1"; shift; fi
  p="$(_oproj "$proj")" || return 1
  if [[ ! -f "$p/constraint.sdc" ]]; then echo "Error: $p/constraint.sdc not found"; return 1; fi
  orig="$(grep -E '^[[:space:]]*set[[:space:]]+clk_period' "$p/constraint.sdc" | head -1 | awk '{print $3}')"
  if [[ -z "$orig" ]]; then echo "constraint.sdc needs a line: set clk_period <ns>"; return 1; fi

  sdc_bak="$p/constraint.sdc.orig_bak_$$"
  cp "$p/constraint.sdc" "$sdc_bak" || return 1
  trap 'if [[ -f "'"$sdc_bak"'" ]]; then cp -f "'"$sdc_bak"'" "'"$p"'/constraint.sdc"; rm -f "'"$sdc_bak"'"; fi' INT TERM HUP

  _oenv; ev="$OENV_ID"
  printf "%-8s %-10s %-10s %-10s %-5s %s
" period_ns slack_ns power_mW area_um2 DRC source | tee "$p/sweep.txt"
  {
    for per in "$@"; do
      sed -i -E "s/^[[:space:]]*set[[:space:]]+clk_period[[:space:]]+.*/set clk_period $per/" "$p/constraint.sdc"
      ih="$(_ohash "$p")"
      if run="$(_ofind_run "$p" "$ih" "$ev")"; then
        printf "%-8s %-10s %-10s %-10s %-5s %s
" "$per" "$(_ojget "$run/manifest.json" slack_ns)" \
          "$(_ojget "$run/manifest.json" power_mW)" "$(_ojget "$run/manifest.json" area_um2)" \
          "$(_ojget "$run/manifest.json" drc)" "saved ${run:t}" | tee -a "$p/sweep.txt"
        continue
      fi
      _omake "$p" clean_all >/dev/null 2>&1
      if _omake "$p" "results/$(_ovar "$p" PLATFORM)/$(_oname "$p")/base/6_final.gds"; then
        _ometrics "$p"
        printf "%-8s %-10s %-10s %-10s %-5s %s
" "$per" "${SLACK:-?}" "${POWER:-?}" "${AREA:-?}" "${DRC:-?}" built | tee -a "$p/sweep.txt"
      else
        printf "%-8s FAILED (see make.log)
" "$per" | tee -a "$p/sweep.txt"
      fi
    done
  } always {
    if [[ -f "$sdc_bak" ]]; then
      cp -f "$sdc_bak" "$p/constraint.sdc"
      rm -f "$sdc_bak"
    fi
    trap - INT TERM HUP
  }
  echo "(clk_period restored to $orig; negative slack = timing violated)"
}

# self-test
_OT_OK=0; _OT_BAD=0
_ot() {   # _ot "<description>" <command...>
  local d="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  ✓ $d"; _OT_OK=$((_OT_OK+1)); else echo "  ✗ $d"; _OT_BAD=$((_OT_BAD+1)); fi
}
otest() {   # otest [quick] : self-test of the toolkit (quick skips the real flow runs, about 1.5 min without quick)
  _OT_OK=0; _OT_BAD=0
  local T="$ORFS_TOOLS" plat=sky130hd tp td workspace testname
  local h1 h2 h3 h4 h5 h6 h7 r1 rc runs d
  mkdir -p "$ORFS_TMP" || return 1
  workspace="$(mktemp -d "$ORFS_TMP/otest.XXXXXX")" || return 1
  testname="zzotest_$$_$(date +%s)"
  tp="$ORFS_PROJECTS/$testname"
  td="$workspace/hash"

  # Check all exact paths before creating or cleaning test resources.
  if [[ -e "$tp" || -L "$tp" ]]; then
    echo "Refusing to use existing project: $tp"
    rm -rf -- "$workspace"
    return 1
  fi
  for d in results logs reports objects; do
    if [[ -e "$ORFS_FLOW/$d/$plat/$testname" ||
          -L "$ORFS_FLOW/$d/$plat/$testname" ]]; then
      echo "Refusing to use existing ORFS output: $ORFS_FLOW/$d/$plat/$testname"
      rm -rf -- "$workspace"
      return 1
    fi
  done
  echo "▶ static checks"
  _ot "orfs-tools.sh parses" zsh -n "$T/orfs-tools.sh"
  _ot "chipwiz.py compiles" python3 -m py_compile "$T/wizard/chipwiz.py"
  _ot "flow.json is valid" python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$T/wizard/flow.json"
  _ot "gen25d.py compiles" python3 -m py_compile "$T/25d/gen25d.py"
  _ot "odoctor.py compiles" python3 -m py_compile "$T/odoctor.py"
  _ot "odoctor finds no failures" odoctor --quiet
  _ot "yosys runs" "$ORFS_YOSYS" -V
  _ot "openroad runs" /usr/bin/openroad -version
  echo "▶ content hash"
  rm -rf "$td"; mkdir -p "$td/rtl"
  echo "module a; endmodule" > "$td/rtl/a.v"; echo "set clk_period 5.0" > "$td/constraint.sdc"
  printf 'PROJ_DIR = /x/y\nexport DESIGN_NAME = a\n' > "$td/config.mk"
  h1="$(_ohash "$td")"
  sed -i 's|/x/y|/moved/elsewhere|' "$td/config.mk"; h2="$(_ohash "$td")"
  sed -i 's/5.0/4.0/' "$td/constraint.sdc"; h3="$(_ohash "$td")"
  _ot "hash ignores the PROJ_DIR line" test "$h1" = "$h2"
  _ot "hash changes when the SDC changes" test "$h1" != "$h3"

  # Regression: nested headers and RTL must affect the input hash.
  mkdir -p "$td/rtl/sub"
  printf '%s\n' '`define WIDTH 8' > "$td/rtl/sub/defs.svh"
  h4="$(_ohash "$td")"
  printf '%s\n' '`define WIDTH 16' > "$td/rtl/sub/defs.svh"
  h5="$(_ohash "$td")"
  _ot "hash includes nested .svh headers" test "$h4" != "$h5"

  printf '%s\n' 'module nested; endmodule' > "$td/rtl/sub/nested.sv"
  h6="$(_ohash "$td")"
  printf '%s\n' 'module nested; wire a; endmodule' > "$td/rtl/sub/nested.sv"
  h7="$(_ohash "$td")"
  _ot "hash includes nested .sv RTL" test "$h6" != "$h7"

  rm -rf "$td"

  echo "▶ failure detection"
  rm -rf "$tp"; onew $testname $plat 5.0 >/dev/null 2>&1
  _omake "$tp" definitely_not_a_target_xyz >/dev/null 2>&1; rc=$?
  _ot "a failing make returns non-zero" test "$rc" -ne 0
  _ot "no run is saved after a failure" test ! -e "$tp/out/latest"
  printf '%s\n' "ERROR: syntax error, unexpected '}'" > "$workspace/ex_a.log"
  printf '%s\n' "make: *** No rule to make target '/x/constraint.sdc'.  Stop." > "$workspace/ex_b.log"
  printf '%s\n' "everything is fine here" > "$workspace/ex_c.log"
  _ot "error explainer spots a Verilog syntax error" test -n "$(_oexplain "$workspace/ex_a.log" | grep -i 'syntax')"
  _ot "error explainer spots a missing file" test -n "$(_oexplain "$workspace/ex_b.log" | grep -i 'missing')"
  _ot "error explainer stays quiet on a clean log" test -z "$(_oexplain "$workspace/ex_c.log")"
  if [[ "${1:-}" != quick ]]; then
    echo "▶ real flow on a throwaway design (about 1 min)"
    orun $testname >/dev/null 2>&1; rc=$?
    _ot "full flow succeeds" test "$rc" -eq 0
    r1="$(readlink "$tp/out/latest" 2>/dev/null)"
    _ot "a run was saved" test -n "$r1"
    _ot "manifest holds the input hash" grep -q "\"input_hash\": \"$(_ohash "$tp")\"" "$tp/out/$r1/manifest.json"
    _ot "manifest names the toolchain" grep -q '"yosys": "Yosys 0' "$tp/out/$r1/manifest.json"
    _ot "stage records were written" grep -q '^6_final.gds ' "$tp/out/.stages"
    _ot "all 6 stages are fresh" test "$(ostale $testname | grep -c ' fresh$')" -eq 6
    operiod 4.0 $testname >/dev/null 2>&1
    _ot "editing the SDC makes all 6 stale" test "$(ostale $testname | grep -c ' stale$')" -eq 6
    operiod 5.0 $testname >/dev/null 2>&1
    _ot "restoring the SDC text makes them fresh again" test "$(ostale $testname | grep -c ' fresh$')" -eq 6
    echo "▶ sweep reuse"
    osweep $testname 5.0 4.0 > "$workspace/ot_sweep1.txt" 2>&1
    _ot "sweep reuses the saved 5.0 ns run" grep -q '^5.0 .*saved' "$workspace/ot_sweep1.txt"
    _ot "sweep builds the new 4.0 ns period" grep -q '^4.0 .*built' "$workspace/ot_sweep1.txt"
    runs="$(tail -n +2 "$tp/out/runs.tsv" 2>/dev/null | wc -l)"
    _ot "two runs saved so far" test "$runs" -eq 2
    osweep $testname 5.0 4.0 > "$workspace/ot_sweep2.txt" 2>&1
    _ot "second sweep reuses both periods" test "$(grep -c saved "$workspace/ot_sweep2.txt")" -eq 2
    runs="$(tail -n +2 "$tp/out/runs.tsv" 2>/dev/null | wc -l)"
    _ot "no new runs after reuse" test "$runs" -eq 2
    _ot "SDC restored after the sweep" grep -q '^set clk_period 5.0' "$tp/constraint.sdc"
  fi
  # Remove only the uniquely named project/output paths checked above.
  for d in results logs reports objects; do
    rm -rf -- "$ORFS_FLOW/$d/$plat/$testname"
  done
  rm -rf -- "$tp" "$workspace"
  echo; echo "otest: $_OT_OK passed, $_OT_BAD failed"
  (( _OT_BAD == 0 ))
}

# ---- v3.4: odoctor (read-only health check) ----
odoctor() {   # odoctor [-q] [project ...] : check tools, versions, ORFS, platforms, disk, GUI, toolkit and projects
  python3 "$ORFS_TOOLS/odoctor.py" "$@"
}


# Validate a project before launching the ORFS flow.
ocheck() {
  emulate -L zsh
  setopt local_options no_unset

  local project="${1:-}"
  local p config sdc plat design period rtl_count errors=0
  local module_re

  if [[ -z "$project" ]]; then
    if [[ -f "$PWD/config.mk" ]]; then
      p="$PWD"
    else
      print -u2 "Usage: ocheck <project-name-or-directory>"
      return 2
    fi
  elif [[ -d "$project" ]]; then
    p="$(cd "$project" 2>/dev/null && pwd -P)" || {
      print -u2 "ERROR: Cannot access project: $project"
      return 2
    }
  else
    p="${ORFS_PROJECTS:-$PWD/Projects}/$project"
  fi

  if [[ ! -d "$p" ]]; then
    print -u2 "ERROR: Project directory not found: $p"
    return 2
  fi

  config="$p/config.mk"
  sdc="$p/constraint.sdc"

  print "Checking project: $p"

  if [[ ! -f "$config" ]]; then
    print "  FAIL: config.mk is missing"
    (( errors += 1 ))
  else
    design="$(sed -nE \
      's/^[[:space:]]*(export[[:space:]]+)?DESIGN_NAME[[:space:]]*[:?+]?=[[:space:]]*([^[:space:]#]+).*/\2/p' \
      "$config" | head -1)"
    plat="$(sed -nE \
      's/^[[:space:]]*(export[[:space:]]+)?PLATFORM[[:space:]]*[:?+]?=[[:space:]]*([^[:space:]#]+).*/\2/p' \
      "$config" | head -1)"

    if [[ -z "$design" ]]; then
      print "  FAIL: DESIGN_NAME is missing or not a simple literal assignment"
      (( errors += 1 ))
    else
      print "  PASS: DESIGN_NAME=$design"
    fi

    if [[ -z "$plat" ]]; then
      print "  FAIL: PLATFORM is missing or not a simple literal assignment"
      (( errors += 1 ))
    elif [[ "$plat" == */* || "$plat" == "." || "$plat" == ".." ]]; then
      print "  FAIL: PLATFORM must be a platform name, not a path: $plat"
      (( errors += 1 ))
    elif [[ ! -d "${ORFS_FLOW:-$PWD/OpenROAD-flow-scripts/flow}/platforms/$plat" ]]; then
      print "  FAIL: Platform directory not found: $plat"
      (( errors += 1 ))
    else
      print "  PASS: platform directory exists ($plat)"
    fi
  fi

  if [[ ! -f "$sdc" ]]; then
    print "  FAIL: constraint.sdc is missing"
    (( errors += 1 ))
  else
    period="$(sed -nE \
      's/^[[:space:]]*set[[:space:]]+clk_period[[:space:]]+([0-9]+([.][0-9]*)?|[.][0-9]+)([[:space:]#].*)?$/\1/p' \
      "$sdc" | head -1)"
    if [[ -z "$period" ]] || ! awk -v x="$period" 'BEGIN { exit !(x > 0) }'; then
      print "  FAIL: constraint.sdc must define a positive numeric 'set clk_period'"
      (( errors += 1 ))
    else
      print "  PASS: clock period is $period"
    fi
  fi

  if [[ ! -d "$p/rtl" ]]; then
    print "  FAIL: rtl/ directory is missing"
    (( errors += 1 ))
  else
    rtl_count="$(find "$p/rtl" -type f \( \
      -iname '*.v' -o -iname '*.sv' -o -iname '*.vh' -o -iname '*.svh' \
      \) -print | wc -l | tr -d ' ')"
    if (( rtl_count == 0 )); then
      print "  FAIL: no Verilog/SystemVerilog files found under rtl/"
      (( errors += 1 ))
    else
      print "  PASS: found $rtl_count Verilog/SystemVerilog source/header file(s)"
    fi

    if [[ -n "${design:-}" && -n "${plat:-}" ]]; then
      module_re="^[[:space:]]*module[[:space:]]+${design}([[:space:]#(;]|$)"
      if ! find "$p/rtl" -type f \( -iname '*.v' -o -iname '*.sv' \) \
          -exec grep -Eq "$module_re" {} + 2>/dev/null; then
        print "  WARN: no obvious module declaration matching DESIGN_NAME=$design"
        print "        Check whether the top module is generated or declared indirectly."
      else
        print "  PASS: top-module declaration appears to match DESIGN_NAME"
      fi
    fi
  fi

  # The clock port named in the SDC must exist in the RTL
  if [[ -f "$sdc" && -d "$p/rtl" ]]; then
    local clkport
    clkport="$(sed -nE 's/^[[:space:]]*create_clock.*get_ports[[:space:]]+\{?([A-Za-z_][A-Za-z0-9_]*)\}?.*/\1/p' "$sdc" | head -1)"
    if [[ -n "$clkport" ]]; then
      if grep -rqw --include='*.v' --include='*.sv' -- "$clkport" "$p/rtl" 2>/dev/null; then
        print "  PASS: clock port '$clkport' from the SDC appears in the RTL"
      else
        print "  FAIL: the SDC clocks port '$clkport' but no RTL file mentions it"
        print "        (name the clock input in the RTL exactly as in constraint.sdc, otherwise timing is never checked)"
        (( errors += 1 ))
      fi
    fi
  fi

  if (( errors > 0 )); then
    print "Preflight result: FAIL ($errors issue(s))"
    return 1
  fi

  print "Preflight result: PASS"
  return 0
}


# Run preflight for recognized project targets before starting ORFS.
# The original implementation is retained as _orun_unchecked.
if (( ${+functions[orun]} )) && (( ! ${+functions[_orun_unchecked]} )); then
  functions -c orun _orun_unchecked
fi

orun() {
  local candidate="${1:-}" project=""

  if [[ -n "$candidate" ]]; then
    if [[ -n "${ORFS_PROJECTS:-}" &&
          -d "$ORFS_PROJECTS/$candidate" &&
          "$candidate" != */* ]]; then
      project="$ORFS_PROJECTS/$candidate"
    elif [[ -d "$candidate" && -f "$candidate/config.mk" ]]; then
      project="$candidate"
    fi
  fi

  if [[ -n "$project" ]]; then
    ocheck "$project" || return $?
  elif [[ -z "$candidate" ]]; then
    # no argument: find the project the same way the other commands do (walks up from the current folder)
    local up
    up="$(_oproj "" 2>/dev/null)" && { ocheck "$up" || return $?; }
  fi

  _orun_unchecked "$@"
}

# Generate a standalone HTML report from saved run history and artifacts.
oreport() {
  local project="${1:-}"
  local p

  if [[ -z "$project" ]]; then
    if [[ -f "$PWD/config.mk" ]]; then
      p="$PWD"
    else
      print -u2 "Usage: oreport <project-name-or-directory>"
      return 2
    fi
  elif [[ -d "$project" ]]; then
    p="$(cd "$project" 2>/dev/null && pwd -P)" || return 2
  else
    p="${ORFS_PROJECTS:-$PWD/Projects}/$project"
  fi

  if [[ ! -d "$p" ]]; then
    print -u2 "ERROR: Project directory not found: $p"
    return 2
  fi

  python3 "${ORFS_TOOLS:-$PWD/Tools}/oreport.py" "$p"
}

# --- User-friendly path & 2.5D helpers ---
# Allow commands to accept "Projects/foo" or just "foo"
_oproj_clean() {
  local target="${1#Projects/}"
  target="${target%/}"
  if [[ -d "$ORFS_PROJECTS/$target" ]]; then
    echo "$ORFS_PROJECTS/$target"
    return 0
  fi
  echo "Project not found: $1" >&2
  return 1
}

# 2.5D view shorthand: o25d <project> opens the KLayout 2.5D view (same as o3d).
# Accepts "foo", "Projects/foo" or "Projects/foo/".
o25d() {
  local t="${1#Projects/}"
  t="${t%/}"
  o3d "$t"
}
