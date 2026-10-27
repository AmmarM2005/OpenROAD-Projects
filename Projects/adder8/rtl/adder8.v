// ===== RTL for adder8 =====
module adder8 (
    input  wire       clk,        // required by the template (unused: adder is combinational)
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire       cin,
    output wire [7:0] sum,
    output wire       cout
);

    // 9-bit concatenation captures the carry-out automatically
    assign {cout, sum} = a + b + cin;

endmodule