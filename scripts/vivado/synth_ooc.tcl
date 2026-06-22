set root_dir $::env(ITCH_ROOT)
set rtl_dir $::env(ITCH_RTL_DIR)
set out_dir $::env(ITCH_SYNTH_OUT_DIR)
set part_name $::env(ITCH_VIVADO_PART)
set clock_mhz $::env(ITCH_CLOCK_MHZ)
set clock_period_ns [expr {1000.0 / double($clock_mhz)}]

file mkdir $out_dir

read_verilog -sv [file join $rtl_dir itch_parser_pkg.sv]
read_verilog -sv [file join $rtl_dir itch_parser_core.sv]

set xdc_file [file join $out_dir itch_parser_core_ooc.xdc]
set xdc [open $xdc_file w]
puts $xdc [format {create_clock -name clk -period %.3f [get_ports clk]} $clock_period_ns]
close $xdc
read_xdc $xdc_file

synth_design -top itch_parser_core -part $part_name -mode out_of_context

report_utilization -file [file join $out_dir utilization.rpt]
report_timing_summary -file [file join $out_dir timing_summary.rpt]
report_clock_utilization -file [file join $out_dir clock_utilization.rpt]

write_checkpoint -force [file join $out_dir itch_parser_core_synth.dcp]
write_verilog -force -mode funcsim [file join $out_dir itch_parser_core_synth.v]

if {![catch {write_sdf -force [file join $out_dir itch_parser_core_synth.sdf]} sdf_error]} {
  puts "Wrote synthesized SDF."
} else {
  puts "SDF export skipped: $sdf_error"
}

puts "Synthesized itch_parser_core for $part_name at ${clock_mhz}MHz."
puts "Reports written to $out_dir."
