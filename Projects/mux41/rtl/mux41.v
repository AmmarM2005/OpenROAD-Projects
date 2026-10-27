// ===== RTL for mux41 (Registered Output) =====
module mux41 (
    input  wire       clk,
    input  wire [1:0] sel,
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire [7:0] c,
    input  wire [7:0] d,
    output reg  [7:0] y
);

    always @(posedge clk) begin
        case (sel)
            2'b00:   y <= a;
            2'b01:   y <= b;
            2'b10:   y <= c;
            2'b11:   y <= d;
            default: y <= 8'b0;
        endcase
    end

endmodule