module rx #(
    parameter logic [3:0] WIDTH = 8  
)(
    input logic clk,
    input logic rst,
    input logic rxd
);
  logic rx_c, rx_s;

  fifo #(.WIDTH (WIDTH)) i_fifo(
    .clk (clk),
    .rst (rst)
  );

  assign rx_s = rxd;
  
endmodule