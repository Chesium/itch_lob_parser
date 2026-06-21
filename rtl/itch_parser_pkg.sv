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

  typedef enum logic [3:0] {
    FIELD_NONE,
    FIELD_STOCK_LOCATE,
    FIELD_TRACKING_NUMBER,
    FIELD_TIMESTAMP,
    FIELD_ORDER_REF,
    FIELD_NEW_ORDER_REF,
    FIELD_SIDE,
    FIELD_QTY,
    FIELD_PRICE,
    FIELD_MATCH_NUMBER,
    FIELD_STOCK
  } field_id_t;

  typedef struct packed {
    field_id_t  field;
    logic [5:0] start;
    logic [5:0] len;
  } field_desc_t;

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

  localparam logic [5:0] OFF_STOCK_LOCATE = 6'd1;
  localparam logic [5:0] OFF_TRACKING_NUMBER = 6'd3;
  localparam logic [5:0] OFF_TIMESTAMP = 6'd5;
  localparam logic [5:0] OFF_ORDER_REF = 6'd11;

  localparam logic [5:0] OFF_ADD_SIDE = 6'd19;
  localparam logic [5:0] OFF_ADD_QTY = 6'd20;
  localparam logic [5:0] OFF_ADD_STOCK = 6'd24;
  localparam logic [5:0] OFF_ADD_PRICE = 6'd32;

  localparam logic [5:0] OFF_EXEC_QTY = 6'd19;
  localparam logic [5:0] OFF_EXEC_MATCH_NUMBER = 6'd23;

  localparam logic [5:0] OFF_CANCEL_QTY = 6'd19;

  localparam logic [5:0] OFF_REPLACE_NEW_ORDER_REF = 6'd19;
  localparam logic [5:0] OFF_REPLACE_QTY = 6'd27;
  localparam logic [5:0] OFF_REPLACE_PRICE = 6'd31;

  localparam logic [5:0] LEN_U16 = 6'd2;
  localparam logic [5:0] LEN_U32 = 6'd4;
  localparam logic [5:0] LEN_U48 = 6'd6;
  localparam logic [5:0] LEN_U64 = 6'd8;
  localparam logic [5:0] LEN_SIDE = 6'd1;
  localparam logic [5:0] LEN_STOCK = 6'd8;

  localparam int unsigned COMMON_FIELD_COUNT = 4;
  localparam int unsigned ADD_FIELD_COUNT = 4;
  localparam int unsigned EXEC_FIELD_COUNT = 2;
  localparam int unsigned CANCEL_FIELD_COUNT = 1;
  localparam int unsigned DELETE_FIELD_COUNT = 0;
  localparam int unsigned REPLACE_FIELD_COUNT = 3;

  function automatic field_desc_t make_field_desc(input field_id_t field, input logic [5:0] start,
                                                  input logic [5:0] len);
    field_desc_t desc;
    begin
      desc.field = field;
      desc.start = start;
      desc.len   = len;
      return desc;
    end
  endfunction

  function automatic field_desc_t null_field_desc();
    begin
      return make_field_desc(FIELD_NONE, 0, 0);
    end
  endfunction

  function automatic field_desc_t common_field_desc(input int unsigned index);
    begin
      unique case (index)
        0: return make_field_desc(FIELD_STOCK_LOCATE, OFF_STOCK_LOCATE, LEN_U16);
        1: return make_field_desc(FIELD_TRACKING_NUMBER, OFF_TRACKING_NUMBER, LEN_U16);
        2: return make_field_desc(FIELD_TIMESTAMP, OFF_TIMESTAMP, LEN_U48);
        3: return make_field_desc(FIELD_ORDER_REF, OFF_ORDER_REF, LEN_U64);
        default: return null_field_desc();
      endcase
    end
  endfunction

  function automatic int unsigned msg_field_count(input msg_kind_t kind);
    begin
      unique case (kind)
        MSG_ADD:     return ADD_FIELD_COUNT;
        MSG_EXECUTE: return EXEC_FIELD_COUNT;
        MSG_CANCEL:  return CANCEL_FIELD_COUNT;
        MSG_DELETE:  return DELETE_FIELD_COUNT;
        MSG_REPLACE: return REPLACE_FIELD_COUNT;
        default:     return 0;
      endcase
    end
  endfunction

  function automatic field_desc_t msg_field_desc(input msg_kind_t kind, input int unsigned index);
    begin
      unique case (kind)
        MSG_ADD: begin
          unique case (index)
            0: return make_field_desc(FIELD_SIDE, OFF_ADD_SIDE, LEN_SIDE);
            1: return make_field_desc(FIELD_QTY, OFF_ADD_QTY, LEN_U32);
            2: return make_field_desc(FIELD_STOCK, OFF_ADD_STOCK, LEN_STOCK);
            3: return make_field_desc(FIELD_PRICE, OFF_ADD_PRICE, LEN_U32);
            default: return null_field_desc();
          endcase
        end
        MSG_EXECUTE: begin
          unique case (index)
            0: return make_field_desc(FIELD_QTY, OFF_EXEC_QTY, LEN_U32);
            1: return make_field_desc(FIELD_MATCH_NUMBER, OFF_EXEC_MATCH_NUMBER, LEN_U64);
            default: return null_field_desc();
          endcase
        end
        MSG_CANCEL: begin
          unique case (index)
            0: return make_field_desc(FIELD_QTY, OFF_CANCEL_QTY, LEN_U32);
            default: return null_field_desc();
          endcase
        end
        MSG_REPLACE: begin
          unique case (index)
            0: return make_field_desc(FIELD_NEW_ORDER_REF, OFF_REPLACE_NEW_ORDER_REF, LEN_U64);
            1: return make_field_desc(FIELD_QTY, OFF_REPLACE_QTY, LEN_U32);
            2: return make_field_desc(FIELD_PRICE, OFF_REPLACE_PRICE, LEN_U32);
            default: return null_field_desc();
          endcase
        end
        default: return null_field_desc();
      endcase
    end
  endfunction

  function automatic logic is_in_field(input logic [5:0] offset, input logic [5:0] start,
                                       input logic [5:0] len);
    begin
      return (offset >= start) && (offset < (start + len));
    end
  endfunction

  function automatic int unsigned be_lsb(input logic [5:0] offset, input logic [5:0] start,
                                         input logic [5:0] len);
    logic [5:0] byte_index;
    begin
      byte_index = offset - start;
      return 8 * (int'(len) - 1 - int'(byte_index));
    end
  endfunction

  function automatic logic is_in_desc(input logic [5:0] offset, input field_desc_t desc);
    begin
      return (desc.field != FIELD_NONE) && is_in_field(offset, desc.start, desc.len);
    end
  endfunction

  function automatic int unsigned desc_be_lsb(input logic [5:0] offset, input field_desc_t desc);
    begin
      return be_lsb(offset, desc.start, desc.len) + ((desc.field == FIELD_NONE) ? 0 : 0);
    end
  endfunction

  function automatic void find_common_field(input logic [5:0] offset, output field_desc_t desc,
                                            output logic found);
    field_desc_t candidate;
    begin
      desc  = null_field_desc();
      found = 1'b0;
      for (int unsigned i = 0; i < COMMON_FIELD_COUNT; i++) begin
        candidate = common_field_desc(i);
        if (!found && is_in_desc(offset, candidate)) begin
          desc  = candidate;
          found = 1'b1;
        end
      end
    end
  endfunction

  function automatic void find_msg_field(input msg_kind_t kind, input logic [5:0] offset,
                                         output field_desc_t desc, output logic found);
    field_desc_t candidate;
    begin
      desc  = null_field_desc();
      found = 1'b0;
      for (int unsigned i = 0; i < 4; i++) begin
        if (i < msg_field_count(kind)) begin
          candidate = msg_field_desc(kind, i);
          if (!found && is_in_desc(offset, candidate)) begin
            desc  = candidate;
            found = 1'b1;
          end
        end
      end
    end
  endfunction

  function automatic void find_active_field(input msg_kind_t kind, input logic [5:0] offset,
                                            output field_desc_t desc, output logic found);
    field_desc_t common_desc;
    field_desc_t message_desc;
    logic        common_found;
    logic        message_found;
    begin
      find_common_field(offset, common_desc, common_found);
      find_msg_field(kind, offset, message_desc, message_found);
      if (common_found) begin
        desc  = common_desc;
        found = 1'b1;
      end else begin
        desc  = message_desc;
        found = message_found;
      end
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
