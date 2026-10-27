
# Project location (kept up to date automatically by the toolkit)
PROJ_DIR = /home/ammar/Ammar_Linux/OpenROAD/Projects/adder8

# Only a few lines ever change between designs.
# DESIGN_NAME must equal the top module name in your RTL.
export DESIGN_NICKNAME = adder8
export DESIGN_NAME     = adder8
export PLATFORM        = sky130hd

export VERILOG_FILES = $(sort $(wildcard $(PROJ_DIR)/rtl/*.v) $(wildcard $(PROJ_DIR)/rtl/*.sv))
export SDC_FILE      = $(PROJ_DIR)/constraint.sdc

# Die and core dimensions (um)
export DIE_AREA  = 0 0 100 100
export CORE_AREA = 10 10 90 90

# Placement density adjustment
export PLACE_DENSITY_LB_ADDON = 0.10
