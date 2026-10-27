// Starter design (a registered 8-bit adder). Replace with your own RTL.
// The top module name must match DESIGN_NAME in config.mk.
module demo (
    input  wire       clk,
    input  wire [7:0] a,
    input  wire [7:0] b,
    output reg  [8:0] sum
);
    always @(posedge clk) sum <= {1'b0, a} + {1'b0, b};
endmodule
