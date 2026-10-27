module counter4bit (
    input  wire       clk,
    input  wire       rst,
    output reg  [3:0] q
);
    always @(posedge clk) q <= rst ? 4'd0 : q + 4'd1;
endmodule