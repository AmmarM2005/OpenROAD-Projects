# Project location (kept up to date automatically by the toolkit)
PROJ_DIR = /home/ammar/Ammar_Linux/OpenROAD/Projects/mux32

# Only a few lines ever change between designs.
# DESIGN_NAME must equal the top module name in your RTL.
export DESIGN_NICKNAME = mux32
export DESIGN_NAME     = mux32
export PLATFORM        = sky130hd

export VERILOG_FILES = $(sort $(wildcard $(PROJ_DIR)/rtl/*.v) $(wildcard $(PROJ_DIR)/rtl/*.sv))
export SDC_FILE      = $(PROJ_DIR)/constraint.sdc

# Die size, pick ONE option. Option A: fixed die in um (good for tiny designs).
export DIE_AREA  = 0 0 120 120
export CORE_AREA = 10 10 110 110
# Option B (bigger designs, e.g. a CPU): comment out the two lines above, uncomment:
# export CORE_UTILIZATION = 30

export PLACE_DENSITY_LB_ADDON = 0.20
