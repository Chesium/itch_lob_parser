
module itch_parser_core (

    input logic clk,   // Synchronous clock
    input logic rst_n, // System reset, active low

    // Slave IN interface - Byte-oriented simplified ITCH payload stream
    output logic s_axis_tready,  // Ready to accept data in
    input logic [7:0] s_axis_tdata,  // Data in
    input logic s_axis_tlast,  // Optional data in qualifier
    input logic s_axis_tvalid,  // Data in is valid

    // Normalized event output
    output logic evt_valid,
    input  logic evt_ready,

    output logic [ 2:0] evt_kind,
    output logic [15:0] stock_locate,
    output logic [15:0] tracking_number,
    output logic [47:0] timestamp,

    output logic [63:0] order_ref,
    output logic [63:0] new_order_ref,
    output logic        side,
    output logic [31:0] qty,
    output logic [31:0] price,
    output logic [63:0] match_number,
    output logic [63:0] stock,
    output logic [ 7:0] valid_mask,

    output logic       error_valid,
    output logic [7:0] error_code
);

  // Define the axis_states of axis_state machine (one hot encoding)
  localparam integer Idle = 4'b1000;
  localparam integer ReadInputs = 4'b0100;
  localparam integer Compute = 4'b0010;
  localparam integer WriteOutputs = 4'b0001;

  localparam integer MsgAdd = 3'd0;
  localparam integer MsgExecute = 3'd1;
  localparam integer MsgCancel = 3'd2;
  localparam integer MsgDelete = 3'd3;
  localparam integer MsgReplace = 3'd4;
  localparam integer MsgError = 3'd7;

  reg [3:0] axis_state;

  reg [5:0] offset;

  logic update_evt_kind;
  assign update_evt_kind = offset == 0;
  logic update_stock_locate;
  logic offset_stock_locate;
  assign update_stock_locate = offset >= 1 && offset < 3;
  assign offset_stock_locate = offset - 1;
  logic update_tracking_number;
  logic offset_tracking_number;
  assign update_tracking_number = offset >= 3 && offset < 5;
  assign offset_tracking_number = offset - 3;
  logic update_timestamp;
  logic [2:0] offset_timestamp;
  assign update_timestamp = offset >= 5 && offset < 11;
  assign offset_timestamp = offset - 5;
  logic update_order_ref;
  logic [2:0] offset_order_ref;
  assign update_order_ref = offset >= 11 && offset < 19;
  assign offset_timestamp = offset - 11;
  logic update_new_order_ref;
  logic [2:0] offset_new_order_ref;
  assign update_new_order_ref = evt_kind == MsgReplace && offset >= 19 && offset < 27;
  assign offset_new_order_ref = offset - 19;
  logic update_side;
  assign update_side = evt_kind == MsgAdd && offset == 19;
  logic update_qty;
  logic [1:0] offset_qty;
  assign update_qty = (evt_kind == MsgAdd      && offset >= 20 && offset < 24)
                   || (evt_kind == MsgExecute  && offset >= 19 && offset < 23)
                   || (evt_kind == MsgCancel   && offset >= 19 && offset < 23)
                   || (evt_kind == MsgReplace  && offset >= 27 && offset < 31);
  assign offset_qty = evt_kind == MsgAdd     ? offset - 20
                    : evt_kind == MsgReplace ? offset - 27
                    : offset - 19;
  logic update_price;
  logic [1:0] offset_price;
  assign update_price = (evt_kind == MsgAdd      && offset >= 32 && offset < 36)
                     || (evt_kind == MsgReplace  && offset >= 31 && offset < 35);
  assign offset_price = evt_kind == MsgAdd ? offset - 32 : offset - 31;
  logic update_match_number;
  logic [2:0] offset_match_number;
  assign update_match_number = evt_kind == MsgExecute && offset >= 23 && offset < 31;
  assign offset_match_number = offset - 23;
  logic update_stock;
  logic [2:0] offset_stock;
  assign update_stock = evt_kind == MsgAdd && offset >= 24 && offset < 32;
  assign offset_stock = offset - 24;

  always_ff @(clk) begin
    if (!rst_n) begin
      axis_state <= Idle;
    end else begin
      case (axis_state)
        Idle: begin
          s_axis_tready <= 0;
          evt_valid <= 0;
          error_valid <= 0;
          if (s_axis_tvalid == 1) begin
            axis_state <= ReadInputs;
            s_axis_tready <= 1;
            offset <= 0;
          end
        end
        ReadInputs: begin
          s_axis_tready <= 1;
          if (s_axis_tvalid == 1) begin
            if (update_evt_kind) begin
              case (s_axis_tdata)
                8'd65: begin  // A: Add
                  evt_kind <= MsgAdd;
                end
                8'd69: begin  // E: Execute
                  evt_kind <= MsgExecute;
                end
                8'd88: begin  // X: Cancel
                  evt_kind <= MsgCancel;
                end
                8'd68: begin  // D: Delete
                  evt_kind <= MsgDelete;
                end
                8'd85: begin  // U: Replace
                  evt_kind <= MsgReplace;
                end
                default: begin  // Other => Error
                  evt_kind <= MsgError;
                end
              endcase
            end
            if (update_stock_locate)
              stock_locate[offset_stock_locate*8+:8] <= s_axis_tdata;
            if (update_tracking_number)
              tracking_number[offset_tracking_number*8+:8] <= s_axis_tdata;
            if (update_timestamp)
              timestamp[offset_timestamp*8+:8] <= s_axis_tdata;
            if (update_order_ref)
              order_ref[offset_order_ref*8+:8] <= s_axis_tdata;
            if (update_new_order_ref)
              new_order_ref[offset_new_order_ref*8+:8] <= s_axis_tdata;
            if (update_side)
              case (s_axis_tdata)
                8'd66 : begin // B: Buy
                  side <= 0;
                end
                8'd83 : begin // S: Sell
                  side <= 1;
                end
                default: begin  // Other => Error
                end
              endcase
            if (update_qty)
              qty[offset_qty*8+:8] <= s_axis_tdata;
            if (update_price)
              price[offset_price*8+:8] <= s_axis_tdata;
            if (update_match_number)
              match_number[offset_match_number*8+:8] <= s_axis_tdata;
            if (update_stock)
              stock[offset_stock*8+:8] <= s_axis_tdata;
          end
        end
        default: begin
        end
      endcase
    end
  end


endmodule
