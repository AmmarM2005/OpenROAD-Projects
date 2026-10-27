
# ==========================================
# SDC Constraints - 8-bit Adder
# ==========================================

# Clock configuration
set clk_period 6.0
set io_delay   [expr {$clk_period * 0.2}]

# Create primary clock
create_clock -name core_clock \
    -period $clk_period \
    [get_ports clk]

# Clock uncertainty (setup margin)
set_clock_uncertainty 0.10 [get_clocks core_clock]

# Clock transition time
set_clock_transition 0.10 [get_clocks core_clock]

# Input delays (excluding clock port)
set_input_delay $io_delay \
    -clock core_clock \
    [delete_from_list [all_inputs] [get_ports clk]]

# Output delays
set_output_delay $io_delay \
    -clock core_clock \
    [all_outputs]
