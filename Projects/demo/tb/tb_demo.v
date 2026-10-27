`timescale 1ns/1ps
module tb_demo;
    reg clk = 0;
    reg [7:0] a, b;
    wire [8:0] sum;
    integer i, errors;
    demo dut (.clk(clk), .a(a), .b(b), .sum(sum));
    always #5 clk = ~clk;
    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, tb_demo);
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
