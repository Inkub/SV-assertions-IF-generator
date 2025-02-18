module top #(
    parameter logic [3:0] WIDTH = 8  
)(
    input logic clk,
    input logic rst,
    input logic [WIDTH-1:0] data_in,
    output logic [WIDTH-1:0] data_out,
    inout keys_s ctrl
);
  logic [1:0]   addr_c, addr_s;
  logic [c_VERY_LOOONG_ADDR - 1 : 0] laddr_c, laddr_s;
  logic         start_c, start_s;
  logic         we_s;
  data_t        data_c, data_s;

  tx #(.WIDTH (WIDTH)) i_tx(
    .clk (clk),
    .rst (rst)
  );

  rx #(.WIDTH (WIDTH)) i_rx(
    .clk (clk),
    .rst (rst)
  );

endmodule