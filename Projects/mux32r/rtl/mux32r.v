module mux32r (
    input  wire        clk,
    input  wire [31:0] d,
    input  wire [4:0]  sel,
    output reg         y
);
    reg [31:0] d_q;
    reg [4:0]  sel_q;
    always @(posedge clk) begin
        d_q   <= d;
        sel_q <= sel;
        y     <= d_q[sel_q];
    end
endmodule
