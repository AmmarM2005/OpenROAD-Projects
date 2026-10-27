module mux32 (
    input  wire        clk,
    input  wire [31:0] d,
    input  wire [4:0]  sel,
    output reg         y
);
    always @(posedge clk) y <= d[sel];
endmodule
