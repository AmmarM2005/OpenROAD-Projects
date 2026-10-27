`timescale 1ns/1ps
module tb_mux32;
    reg clk = 0;
    reg [31:0] d;
    reg [4:0] sel;
    wire y;
    integer i, errors;
    mux32 dut (.clk(clk), .d(d), .sel(sel), .y(y));
    always #5 clk = ~clk;
    initial begin
        errors = 0;
        $dumpfile("mux32.vcd");
        $dumpvars(0, tb_mux32);
        for (i = 0; i < 32; i = i + 1) begin
            d = 32'h1 << i;  sel = i;
            @(posedge clk); #1;
            if (y !== 1'b1) begin errors = errors + 1; $display("FAIL sel=%0d expected 1", i); end
            sel = (i + 1) % 32;
            @(posedge clk); #1;
            if (y !== 1'b0) begin errors = errors + 1; $display("FAIL sel=%0d expected 0", (i + 1) % 32); end
        end
        if (errors == 0) $display("PASS: all 32 inputs selected correctly");
        else $display("FAILED with %0d errors", errors);
        $finish;
    end
endmodule
