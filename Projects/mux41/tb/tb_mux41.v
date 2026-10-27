`timescale 1ns/1ps
// Testbench for mux41: drive inputs, check outputs, print PASS or FAIL.
module tb_mux41;
    reg clk = 0;
    always #5 clk = ~clk;          // 100 MHz clock (period = 10ns)

    // Signals to interface with DUT
    reg  [1:0] sel;
    reg  [7:0] a, b, c, d;
    wire [7:0] y;

    // Instantiate Device Under Test (DUT)
    mux41 dut (
        .clk(clk),
        .sel(sel),
        .a(a),
        .b(b),
        .c(c),
        .d(d),
        .y(y)
    );

    integer errors = 0;
    reg [7:0] expected_val;

    // Task to drive inputs and verify output after clock transition
    task check_mux(
        input [1:0] s_in,
        input [7:0] a_in,
        input [7:0] b_in,
        input [7:0] c_in,
        input [7:0] d_in,
        input [7:0] exp
    );
    begin
        // Apply inputs on negative edge so setup time is clean
        @(negedge clk);
        sel = s_in;
        a   = a_in;
        b   = b_in;
        c   = c_in;
        d   = d_in;
        expected_val = exp;

        // Sample and verify immediately after the next posedge
        @(posedge clk);
        #1; // small hold time delta to read registered output
        if (y !== expected_val) begin
            $display("[FAIL] Time=%0t | sel=%b | a=%h b=%h c=%h d=%h | Expected=%h, Got=%h",
                     $time, sel, a, b, c, d, expected_val, y);
            errors = errors + 1;
        end else begin
            $display("[OK]   Time=%0t | sel=%b | Got expected output=%h", $time, sel, y);
        end
    end
    endtask

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, tb_mux41);

        // Initialize inputs
        sel = 2'b00;
        a   = 8'h00;
        b   = 8'h00;
        c   = 8'h00;
        d   = 8'h00;
        
        // Wait 2 clock cycles before starting tests
        repeat(2) @(posedge clk);

        // Test 1: Select input 'a'
        check_mux(2'b00, 8'hAA, 8'hBB, 8'hCC, 8'hDD, 8'hAA);

        // Test 2: Select input 'b'
        check_mux(2'b01, 8'h11, 8'h22, 8'h33, 8'h44, 8'h22);

        // Test 3: Select input 'c'
        check_mux(2'b10, 8'h55, 8'h66, 8'h77, 8'h88, 8'h77);

        // Test 4: Select input 'd'
        check_mux(2'b11, 8'hDE, 8'hAD, 8'hBE, 8'hEF, 8'hEF);

        // Extra check: modify unselected inputs to ensure isolation
        check_mux(2'b01, 8'hFF, 8'h42, 8'hFF, 8'hFF, 8'h42);

        // Finish sequence
        @(negedge clk);
        if (errors == 0) $display("PASS");
        else             $display("FAILED: %0d errors", errors);
        $finish;
    end
endmodule