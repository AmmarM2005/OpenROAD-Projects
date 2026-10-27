`timescale 1ns/1ps
// Testbench for adder8: drive inputs, check outputs, print PASS or FAIL.
module tb_adder8;
    reg clk = 0;
    always #5 clk = ~clk;          // 100 MHz clock

    // ---- signals ----
    reg  [7:0] a, b;
    reg        cin;
    wire [7:0] sum;
    wire       cout;

    // ---- DUT ----
    adder8 dut (
        .clk  (clk),
        .a    (a),
        .b    (b),
        .cin  (cin),
        .sum  (sum),
        .cout (cout)
    );

    integer   errors = 0;
    integer   i;
    reg [8:0] expected;

    // ---- one stimulus + check ----
    task check;
        input [7:0] ta;
        input [7:0] tb_;
        input       tc;
        begin
            a   = ta;
            b   = tb_;
            cin = tc;
            #10;                                   // let combinational logic settle
            expected = ta + tb_ + tc;
            if ({cout, sum} !== expected) begin
                errors = errors + 1;
                $display("MISMATCH @%0t: a=%0d b=%0d cin=%0b -> cout=%0b sum=%0d | expected %0d",
                         $time, ta, tb_, tc, cout, sum, expected);
            end
        end
    endtask

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, tb_adder8);

        // ---- directed corner cases ----
        check(8'd0,   8'd0,   1'b0);   // zero
        check(8'd0,   8'd0,   1'b1);   // carry-in only
        check(8'd1,   8'd1,   1'b0);
        check(8'd1,   8'd1,   1'b1);
        check(8'd127, 8'd128, 1'b0);   // 255, no carry
        check(8'd255, 8'd0,   1'b0);   // max, no carry
        check(8'd255, 8'd0,   1'b1);   // 256 -> cout=1, sum=0
        check(8'd255, 8'd255, 1'b0);   // 510 -> cout=1, sum=254
        check(8'd255, 8'd255, 1'b1);   // 511 -> cout=1, sum=255
        check(8'd128, 8'd128, 1'b1);   // 257 -> cout=1, sum=1

        // ---- randomized vectors ----
        for (i = 0; i < 200; i = i + 1)
            check($random, $random, $random);

        if (errors == 0) $display("PASS");
        else             $display("FAILED: %0d errors", errors);
        $finish;
    end
endmodule