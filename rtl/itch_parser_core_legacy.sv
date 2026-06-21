module itch_parser_core_legacy (

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

  localparam logic [2:0] MSG_ADD = 3'd0;
  localparam logic [2:0] MSG_EXECUTE = 3'd1;
  localparam logic [2:0] MSG_CANCEL = 3'd2;
  localparam logic [2:0] MSG_DELETE = 3'd3;
  localparam logic [2:0] MSG_REPLACE = 3'd4;
  localparam logic [2:0] MSG_ERROR = 3'd7;

  localparam logic [7:0] MASK_ADD = 8'b01011101;
  localparam logic [7:0] MASK_EXECUTE = 8'b00101001;
  localparam logic [7:0] MASK_CANCEL = 8'b00001001;
  localparam logic [7:0] MASK_DELETE = 8'b00000001;
  localparam logic [7:0] MASK_REPLACE = 8'b00011011;

  localparam logic [7:0] ERR_NONE = 8'd0;
  localparam logic [7:0] ERR_UNKNOWN_TYPE = 8'd1;
  localparam logic [7:0] ERR_BAD_SIDE = 8'd2;
  localparam logic [7:0] ERR_EARLY_TLAST = 8'd3;

  typedef enum logic [1:0] {
    ST_IDLE,
    ST_READ,
    ST_OUTPUT
  } state_t;

  state_t       state;

  logic   [5:0] offset;
  logic   [5:0] msg_len;
  logic         error_pending;

  wire          accept_byte = s_axis_tvalid && s_axis_tready;
  wire          last_byte = accept_byte && (offset == (msg_len - 6'd1));

  assign s_axis_tready = (state == ST_IDLE) || (state == ST_READ);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state           <= ST_IDLE;
      offset          <= 6'd0;
      msg_len         <= 6'd0;
      error_pending   <= 1'b0;
      evt_valid       <= 1'b0;
      evt_kind        <= MSG_ERROR;
      stock_locate    <= 16'd0;
      tracking_number <= 16'd0;
      timestamp       <= 48'd0;
      order_ref       <= 64'd0;
      new_order_ref   <= 64'd0;
      side            <= 1'b0;
      qty             <= 32'd0;
      price           <= 32'd0;
      match_number    <= 64'd0;
      stock           <= 64'd0;
      valid_mask      <= 8'd0;
      error_valid     <= 1'b0;
      error_code      <= ERR_NONE;
    end else begin
      case (state)
        ST_IDLE: begin
          evt_valid     <= 1'b0;
          error_valid   <= 1'b0;
          error_code    <= ERR_NONE;
          error_pending <= 1'b0;

          if (accept_byte) begin
            offset          <= 6'd1;
            stock_locate    <= 16'd0;
            tracking_number <= 16'd0;
            timestamp       <= 48'd0;
            order_ref       <= 64'd0;
            new_order_ref   <= 64'd0;
            side            <= 1'b0;
            qty             <= 32'd0;
            price           <= 32'd0;
            match_number    <= 64'd0;
            stock           <= 64'd0;

            unique case (s_axis_tdata)
              8'h41: begin  // A: Add
                evt_kind   <= MSG_ADD;
                msg_len    <= 6'd36;
                valid_mask <= MASK_ADD;
                state      <= ST_READ;
              end
              8'h45: begin  // E: Execute
                evt_kind   <= MSG_EXECUTE;
                msg_len    <= 6'd31;
                valid_mask <= MASK_EXECUTE;
                state      <= ST_READ;
              end
              8'h58: begin  // X: Cancel
                evt_kind   <= MSG_CANCEL;
                msg_len    <= 6'd23;
                valid_mask <= MASK_CANCEL;
                state      <= ST_READ;
              end
              8'h44: begin  // D: Delete
                evt_kind   <= MSG_DELETE;
                msg_len    <= 6'd19;
                valid_mask <= MASK_DELETE;
                state      <= ST_READ;
              end
              8'h55: begin  // U: Replace
                evt_kind   <= MSG_REPLACE;
                msg_len    <= 6'd35;
                valid_mask <= MASK_REPLACE;
                state      <= ST_READ;
              end
              default: begin
                evt_kind      <= MSG_ERROR;
                msg_len       <= 6'd1;
                valid_mask    <= 8'd0;
                error_valid   <= 1'b1;
                error_code    <= ERR_UNKNOWN_TYPE;
                error_pending <= 1'b1;
                evt_valid     <= 1'b1;
                state         <= ST_OUTPUT;
              end
            endcase
          end
        end

        ST_READ: begin
          if (accept_byte) begin
            if (s_axis_tlast && (offset != (msg_len - 6'd1))) begin
              error_valid   <= 1'b1;
              error_code    <= ERR_EARLY_TLAST;
              error_pending <= 1'b1;
            end

            unique case (offset)
              6'd1:  stock_locate[15:8] <= s_axis_tdata;
              6'd2:  stock_locate[7:0] <= s_axis_tdata;
              6'd3:  tracking_number[15:8] <= s_axis_tdata;
              6'd4:  tracking_number[7:0] <= s_axis_tdata;
              6'd5:  timestamp[47:40] <= s_axis_tdata;
              6'd6:  timestamp[39:32] <= s_axis_tdata;
              6'd7:  timestamp[31:24] <= s_axis_tdata;
              6'd8:  timestamp[23:16] <= s_axis_tdata;
              6'd9:  timestamp[15:8] <= s_axis_tdata;
              6'd10: timestamp[7:0] <= s_axis_tdata;
              6'd11: order_ref[63:56] <= s_axis_tdata;
              6'd12: order_ref[55:48] <= s_axis_tdata;
              6'd13: order_ref[47:40] <= s_axis_tdata;
              6'd14: order_ref[39:32] <= s_axis_tdata;
              6'd15: order_ref[31:24] <= s_axis_tdata;
              6'd16: order_ref[23:16] <= s_axis_tdata;
              6'd17: order_ref[15:8] <= s_axis_tdata;
              6'd18: order_ref[7:0] <= s_axis_tdata;
              default: begin
              end
            endcase

            unique case (evt_kind)
              MSG_ADD: begin
                unique case (offset)
                  6'd19: begin
                    unique case (s_axis_tdata)
                      8'h42: side <= 1'b0;  // B: Buy
                      8'h53: side <= 1'b1;  // S: Sell
                      default: begin
                        error_valid   <= 1'b1;
                        error_code    <= ERR_BAD_SIDE;
                        error_pending <= 1'b1;
                      end
                    endcase
                  end
                  6'd20: qty[31:24] <= s_axis_tdata;
                  6'd21: qty[23:16] <= s_axis_tdata;
                  6'd22: qty[15:8] <= s_axis_tdata;
                  6'd23: qty[7:0] <= s_axis_tdata;
                  6'd24: stock[63:56] <= s_axis_tdata;
                  6'd25: stock[55:48] <= s_axis_tdata;
                  6'd26: stock[47:40] <= s_axis_tdata;
                  6'd27: stock[39:32] <= s_axis_tdata;
                  6'd28: stock[31:24] <= s_axis_tdata;
                  6'd29: stock[23:16] <= s_axis_tdata;
                  6'd30: stock[15:8] <= s_axis_tdata;
                  6'd31: stock[7:0] <= s_axis_tdata;
                  6'd32: price[31:24] <= s_axis_tdata;
                  6'd33: price[23:16] <= s_axis_tdata;
                  6'd34: price[15:8] <= s_axis_tdata;
                  6'd35: price[7:0] <= s_axis_tdata;
                  default: begin
                  end
                endcase
              end

              MSG_EXECUTE: begin
                unique case (offset)
                  6'd19: qty[31:24] <= s_axis_tdata;
                  6'd20: qty[23:16] <= s_axis_tdata;
                  6'd21: qty[15:8] <= s_axis_tdata;
                  6'd22: qty[7:0] <= s_axis_tdata;
                  6'd23: match_number[63:56] <= s_axis_tdata;
                  6'd24: match_number[55:48] <= s_axis_tdata;
                  6'd25: match_number[47:40] <= s_axis_tdata;
                  6'd26: match_number[39:32] <= s_axis_tdata;
                  6'd27: match_number[31:24] <= s_axis_tdata;
                  6'd28: match_number[23:16] <= s_axis_tdata;
                  6'd29: match_number[15:8] <= s_axis_tdata;
                  6'd30: match_number[7:0] <= s_axis_tdata;
                  default: begin
                  end
                endcase
              end

              MSG_CANCEL: begin
                unique case (offset)
                  6'd19: qty[31:24] <= s_axis_tdata;
                  6'd20: qty[23:16] <= s_axis_tdata;
                  6'd21: qty[15:8] <= s_axis_tdata;
                  6'd22: qty[7:0] <= s_axis_tdata;
                  default: begin
                  end
                endcase
              end

              MSG_REPLACE: begin
                unique case (offset)
                  6'd19: new_order_ref[63:56] <= s_axis_tdata;
                  6'd20: new_order_ref[55:48] <= s_axis_tdata;
                  6'd21: new_order_ref[47:40] <= s_axis_tdata;
                  6'd22: new_order_ref[39:32] <= s_axis_tdata;
                  6'd23: new_order_ref[31:24] <= s_axis_tdata;
                  6'd24: new_order_ref[23:16] <= s_axis_tdata;
                  6'd25: new_order_ref[15:8] <= s_axis_tdata;
                  6'd26: new_order_ref[7:0] <= s_axis_tdata;
                  6'd27: qty[31:24] <= s_axis_tdata;
                  6'd28: qty[23:16] <= s_axis_tdata;
                  6'd29: qty[15:8] <= s_axis_tdata;
                  6'd30: qty[7:0] <= s_axis_tdata;
                  6'd31: price[31:24] <= s_axis_tdata;
                  6'd32: price[23:16] <= s_axis_tdata;
                  6'd33: price[15:8] <= s_axis_tdata;
                  6'd34: price[7:0] <= s_axis_tdata;
                  default: begin
                  end
                endcase
              end

              default: begin
              end
            endcase

            if (last_byte) begin
              if (error_pending || error_valid) begin
                evt_kind   <= MSG_ERROR;
                valid_mask <= 8'd0;
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
