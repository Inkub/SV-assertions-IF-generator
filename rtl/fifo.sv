module fifo #(
    parameter logic [3:0] WIDTH = 8  
)(
    input logic clk,
    input logic rst,
    input logic re,
    input logic we,
    input logic[WIDTH-1 : 0] data_in,
    output logic[WIDTH-1 : 0] data_out
);
  logic[WIDTH-1 : 0] data_c, data_s;

  assign data_out = data_s;
  
endmodule