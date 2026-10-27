`timescale 1ns / 1ps

module tb_counter4bit;

    reg clk;
    reg rst;
    wire [3:0] q;

    counter4bit uut (
        .clk(clk),
        .rst(rst),
        .q(q)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst = 1;

        #20;
        rst = 0;

        #180;
        rst = 1;

        #20;
        rst = 0;

        #60;
        $finish;
    end

endmodule