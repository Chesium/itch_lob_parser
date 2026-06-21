package itch_parser_pkg;

  typedef enum logic [2:0] {
    MSG_ADD     = 3'd0,
    MSG_EXECUTE = 3'd1,
    MSG_CANCEL  = 3'd2,
    MSG_DELETE  = 3'd3,
    MSG_REPLACE = 3'd4,
    MSG_ERROR   = 3'd7
  } msg_kind_t;

  typedef struct packed {
    msg_kind_t   kind;
    logic [15:0] stock_locate;
    logic [15:0] tracking_number;
    logic [47:0] timestamp;
    logic [63:0] order_ref;
    logic [63:0] new_order_ref;
    logic        side;
    logic [31:0] qty;
    logic [31:0] price;
    logic [63:0] match_number;
    logic [63:0] stock;
    logic [7:0]  valid_mask;
  } itch_event_t;

  localparam logic [7:0] MASK_ADD = 8'b01011101;
  localparam logic [7:0] MASK_EXECUTE = 8'b00101001;
  localparam logic [7:0] MASK_CANCEL = 8'b00001001;
  localparam logic [7:0] MASK_DELETE = 8'b00000001;
  localparam logic [7:0] MASK_REPLACE = 8'b00011011;

  localparam logic [7:0] ERR_NONE = 8'd0;
  localparam logic [7:0] ERR_UNKNOWN_TYPE = 8'd1;
  localparam logic [7:0] ERR_BAD_SIDE = 8'd2;
  localparam logic [7:0] ERR_EARLY_TLAST = 8'd3;

  localparam logic [5:0] LEN_ADD = 6'd36;
  localparam logic [5:0] LEN_EXECUTE = 6'd31;
  localparam logic [5:0] LEN_CANCEL = 6'd23;
  localparam logic [5:0] LEN_DELETE = 6'd19;
  localparam logic [5:0] LEN_REPLACE = 6'd35;

  localparam int unsigned OFF_STOCK_LOCATE = 1;
  localparam int unsigned OFF_TRACKING_NUMBER = 3;
  localparam int unsigned OFF_TIMESTAMP = 5;
  localparam int unsigned OFF_ORDER_REF = 11;

  localparam int unsigned OFF_ADD_SIDE = 19;
  localparam int unsigned OFF_ADD_QTY = 20;
  localparam int unsigned OFF_ADD_STOCK = 24;
  localparam int unsigned OFF_ADD_PRICE = 32;

  localparam int unsigned OFF_EXEC_QTY = 19;
  localparam int unsigned OFF_EXEC_MATCH_NUMBER = 23;

  localparam int unsigned OFF_CANCEL_QTY = 19;

  localparam int unsigned OFF_REPLACE_NEW_ORDER_REF = 19;
  localparam int unsigned OFF_REPLACE_QTY = 27;
  localparam int unsigned OFF_REPLACE_PRICE = 31;

  localparam int unsigned LEN_U16 = 2;
  localparam int unsigned LEN_U32 = 4;
  localparam int unsigned LEN_U48 = 6;
  localparam int unsigned LEN_U64 = 8;
  localparam int unsigned LEN_SIDE = 1;
  localparam int unsigned LEN_STOCK = 8;

  function automatic logic is_in_field(input logic [5:0] offset, input int unsigned start,
                                       input int unsigned len);
    int unsigned offset_i;
    begin
      offset_i = int'(offset);
      return (offset_i >= start) && (offset_i < (start + len));
    end
  endfunction

  function automatic int unsigned be_lsb(input logic [5:0] offset, input int unsigned start,
                                         input int unsigned len);
    int unsigned byte_index;
    begin
      byte_index = int'(offset) - start;
      return 8 * (len - 1 - byte_index);
    end
  endfunction

  function automatic void decode_msg_type(input logic [7:0] msg_type, output msg_kind_t kind,
                                          output logic [5:0] msg_len, output logic [7:0] mask,
                                          output logic error);
    begin
      error = 1'b0;
      unique case (msg_type)
        8'h41: begin  // A: Add
          kind    = MSG_ADD;
          msg_len = LEN_ADD;
          mask    = MASK_ADD;
        end
        8'h45: begin  // E: Execute
          kind    = MSG_EXECUTE;
          msg_len = LEN_EXECUTE;
          mask    = MASK_EXECUTE;
        end
        8'h58: begin  // X: Cancel
          kind    = MSG_CANCEL;
          msg_len = LEN_CANCEL;
          mask    = MASK_CANCEL;
        end
        8'h44: begin  // D: Delete
          kind    = MSG_DELETE;
          msg_len = LEN_DELETE;
          mask    = MASK_DELETE;
        end
        8'h55: begin  // U: Replace
          kind    = MSG_REPLACE;
          msg_len = LEN_REPLACE;
          mask    = MASK_REPLACE;
        end
        default: begin
          kind    = MSG_ERROR;
          msg_len = 6'd1;
          mask    = 8'd0;
          error   = 1'b1;
        end
      endcase
    end
  endfunction

endpackage
