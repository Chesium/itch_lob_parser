module itch_parser_core (

    input logic clk,   // Synchronous clock
    input logic rst_n, // System reset, active low

    // Slave IN interface - Byte-oriented simplified ITCH payload stream
    output logic       s_axis_tready,  // Ready to accept data in
    input  logic [7:0] s_axis_tdata,   // Data in
    input  logic       s_axis_tlast,   // Optional data in qualifier
    input  logic       s_axis_tvalid,  // Data in is valid

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

  import itch_parser_pkg::*;

  typedef enum logic [1:0] {
    ST_IDLE,
    ST_READ,
    ST_OUTPUT
  } state_t;

  state_t            state;
  itch_event_t       event_q;

  logic        [5:0] msg_len;
  logic        [5:0] offset;
  logic              error_pending;

  msg_kind_t         decoded_kind;
  logic        [5:0] decoded_len;
  logic        [7:0] decoded_mask;
  logic              decoded_error;

  wire               accept_byte = s_axis_tvalid && s_axis_tready;
  wire               last_byte = accept_byte && (offset == (msg_len - 6'd1));

  assign s_axis_tready   = (state == ST_IDLE) || (state == ST_READ);

  assign evt_kind        = event_q.kind;
  assign stock_locate    = event_q.stock_locate;
  assign tracking_number = event_q.tracking_number;
  assign timestamp       = event_q.timestamp;
  assign order_ref       = event_q.order_ref;
  assign new_order_ref   = event_q.new_order_ref;
  assign side            = event_q.side;
  assign qty             = event_q.qty;
  assign price           = event_q.price;
  assign match_number    = event_q.match_number;
  assign stock           = event_q.stock;
  assign valid_mask      = event_q.valid_mask;

  always_comb begin
    decode_msg_type(s_axis_tdata, decoded_kind, decoded_len, decoded_mask, decoded_error);
  end

  function automatic itch_event_t empty_event();
    itch_event_t empty;
    begin
      empty = '0;
      empty.kind = MSG_ERROR;
      return empty;
    end
  endfunction

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state         <= ST_IDLE;
      event_q       <= empty_event();
      msg_len       <= 6'd0;
      offset        <= 6'd0;
      error_pending <= 1'b0;
      evt_valid     <= 1'b0;
      error_valid   <= 1'b0;
      error_code    <= ERR_NONE;
    end else begin
      case (state)
        ST_IDLE: begin
          evt_valid     <= 1'b0;
          error_valid   <= 1'b0;
          error_code    <= ERR_NONE;
          error_pending <= 1'b0;

          if (accept_byte) begin
            event_q            <= empty_event();
            event_q.kind       <= decoded_kind;
            event_q.valid_mask <= decoded_mask;
            msg_len            <= decoded_len;
            offset             <= 6'd1;

            if (decoded_error) begin
              error_valid   <= 1'b1;
              error_code    <= ERR_UNKNOWN_TYPE;
              error_pending <= 1'b1;
              evt_valid     <= 1'b1;
              state         <= ST_OUTPUT;
            end else begin
              state <= ST_READ;
            end
          end
        end

        ST_READ: begin
          if (accept_byte) begin
            if (s_axis_tlast && (offset != (msg_len - 6'd1))) begin
              error_valid   <= 1'b1;
              error_code    <= ERR_EARLY_TLAST;
              error_pending <= 1'b1;
            end

            if (is_in_field(offset, OFF_STOCK_LOCATE, LEN_U16))
              event_q.stock_locate[be_lsb(offset, OFF_STOCK_LOCATE, LEN_U16)+:8] <= s_axis_tdata;
            if (is_in_field(offset, OFF_TRACKING_NUMBER, LEN_U16))
              event_q.tracking_number[be_lsb(
                  offset, OFF_TRACKING_NUMBER, LEN_U16
              )+:8] <= s_axis_tdata;
            if (is_in_field(offset, OFF_TIMESTAMP, LEN_U48))
              event_q.timestamp[be_lsb(offset, OFF_TIMESTAMP, LEN_U48)+:8] <= s_axis_tdata;
            if (is_in_field(offset, OFF_ORDER_REF, LEN_U64))
              event_q.order_ref[be_lsb(offset, OFF_ORDER_REF, LEN_U64)+:8] <= s_axis_tdata;

            unique case (event_q.kind)
              MSG_ADD: begin
                if (is_in_field(offset, OFF_ADD_SIDE, LEN_SIDE)) begin
                  unique case (s_axis_tdata)
                    8'h42: event_q.side <= 1'b0;  // B: Buy
                    8'h53: event_q.side <= 1'b1;  // S: Sell
                    default: begin
                      error_valid   <= 1'b1;
                      error_code    <= ERR_BAD_SIDE;
                      error_pending <= 1'b1;
                    end
                  endcase
                end
                if (is_in_field(offset, OFF_ADD_QTY, LEN_U32))
                  event_q.qty[be_lsb(offset, OFF_ADD_QTY, LEN_U32)+:8] <= s_axis_tdata;
                if (is_in_field(offset, OFF_ADD_STOCK, LEN_STOCK))
                  event_q.stock[be_lsb(offset, OFF_ADD_STOCK, LEN_STOCK)+:8] <= s_axis_tdata;
                if (is_in_field(offset, OFF_ADD_PRICE, LEN_U32))
                  event_q.price[be_lsb(offset, OFF_ADD_PRICE, LEN_U32)+:8] <= s_axis_tdata;
              end

              MSG_EXECUTE: begin
                if (is_in_field(offset, OFF_EXEC_QTY, LEN_U32))
                  event_q.qty[be_lsb(offset, OFF_EXEC_QTY, LEN_U32)+:8] <= s_axis_tdata;
                if (is_in_field(offset, OFF_EXEC_MATCH_NUMBER, LEN_U64))
                  event_q.match_number[be_lsb(
                      offset, OFF_EXEC_MATCH_NUMBER, LEN_U64
                  )+:8] <= s_axis_tdata;
              end

              MSG_CANCEL: begin
                if (is_in_field(offset, OFF_CANCEL_QTY, LEN_U32))
                  event_q.qty[be_lsb(offset, OFF_CANCEL_QTY, LEN_U32)+:8] <= s_axis_tdata;
              end

              MSG_REPLACE: begin
                if (is_in_field(offset, OFF_REPLACE_NEW_ORDER_REF, LEN_U64))
                  event_q.new_order_ref[be_lsb(
                      offset, OFF_REPLACE_NEW_ORDER_REF, LEN_U64
                  )+:8] <= s_axis_tdata;
                if (is_in_field(offset, OFF_REPLACE_QTY, LEN_U32))
                  event_q.qty[be_lsb(offset, OFF_REPLACE_QTY, LEN_U32)+:8] <= s_axis_tdata;
                if (is_in_field(offset, OFF_REPLACE_PRICE, LEN_U32))
                  event_q.price[be_lsb(offset, OFF_REPLACE_PRICE, LEN_U32)+:8] <= s_axis_tdata;
              end

              default: begin
              end
            endcase

            if (last_byte) begin
              if (error_pending || error_valid) begin
                event_q.kind       <= MSG_ERROR;
                event_q.valid_mask <= 8'd0;
              end
              evt_valid <= 1'b1;
              state     <= ST_OUTPUT;
            end else begin
              offset <= offset + 6'd1;
            end
          end
        end

        ST_OUTPUT: begin
          if (evt_ready) begin
            evt_valid   <= 1'b0;
            error_valid <= 1'b0;
            error_code  <= ERR_NONE;
            state       <= ST_IDLE;
          end
        end

        default: begin
          state <= ST_IDLE;
        end
      endcase
    end
  end

endmodule
