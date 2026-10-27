set clk_period 10.0
set io_delay [expr {$clk_period * 0.2}]
create_clock -name core_clock -period $clk_period [get_ports clk]
set_input_delay  $io_delay -clock core_clock [delete_from_list [all_inputs] [get_ports clk]]
set_output_delay $io_delay -clock core_clock [all_outputs]
