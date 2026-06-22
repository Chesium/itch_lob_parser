`timescale 1ns/1ps

module tb_itch_parser_core_xsim;

  localparam int PACKED_EVENT_BITS = 412;
  localparam int MAX_BYTES = 5_000_000;
  localparam int MAX_EVENTS = 200_000;

  parameter int STREAM_BYTES = 0;
  parameter int EXPECTED_EVENTS = 0;
  parameter int VERIFY_EVENTS = 1;
  parameter int INPUT_STALL_PERIOD = 0;
  parameter int OUTPUT_STALL_PERIOD = 0;
  parameter int CLOCK_PERIOD_NS = 10;

  logic clk;
  logic rst_n;

  logic       s_axis_tready;
  logic [7:0] s_axis_tdata;
  logic       s_axis_tlast;
  logic       s_axis_tvalid;

  logic        evt_valid;
  logic        evt_ready;
  logic [ 2:0] evt_kind;
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
  logic [ 7:0] valid_mask;
  logic        error_valid;
  logic [ 7:0] error_code;

  logic [7:0] stream_mem[0:MAX_BYTES-1];
  logic [PACKED_EVENT_BITS-1:0] expected_events[0:MAX_EVENTS-1];

  int byte_index;
  int bytes_accepted;
  int accepted_byte_cycles;
  int events_seen;
  int total_cycles;
  int cycle_count;
  int max_cycles;
  int failures;
  bit started;

  itch_parser_core dut (
      .clk(clk),
      .rst_n(rst_n),
      .s_axis_tready(s_axis_tready),
      .s_axis_tdata(s_axis_tdata),
      .s_axis_tlast(s_axis_tlast),
      .s_axis_tvalid(s_axis_tvalid),
      .evt_valid(evt_valid),
      .evt_ready(evt_ready),
      .evt_kind(evt_kind),
      .stock_locate(stock_locate),
      .tracking_number(tracking_number),
      .timestamp(timestamp),
      .order_ref(order_ref),
      .new_order_ref(new_order_ref),
      .side(side),
      .qty(qty),
      .price(price),
      .match_number(match_number),
      .stock(stock),
      .valid_mask(valid_mask),
      .error_valid(error_valid),
      .error_code(error_code)
  );

  initial begin
    clk = 1'b0;
    forever #(CLOCK_PERIOD_NS / 2.0) clk = ~clk;
  end

  function automatic logic [PACKED_EVENT_BITS-1:0] packed_actual_event();
    begin
      return {
        evt_kind,
        stock_locate,
        tracking_number,
        timestamp,
        order_ref,
        new_order_ref,
        side,
        qty,
        price,
        match_number,
        stock,
        valid_mask
      };
    end
  endfunction

  function automatic bit should_stall(input int period, input int cycle);
    begin
      return (period > 0) && ((cycle % period) == (period - 1));
    end
  endfunction

  task automatic write_result(input bit passed);
    int fh;
    begin
      fh = $fopen("xsim_bench.json", "w");
      if (fh == 0) begin
        $display("ERROR: failed to open result JSON path: xsim_bench.json");
      end else begin
        $fdisplay(fh, "{");
        $fdisplay(fh, "  \"parser\": \"rtl-xsim\",");
        $fdisplay(fh, "  \"passed\": %0s,", passed ? "true" : "false");
        $fdisplay(fh, "  \"bytes\": %0d,", STREAM_BYTES);
        $fdisplay(fh, "  \"bytes_accepted\": %0d,", bytes_accepted);
        $fdisplay(fh, "  \"events\": %0d,", events_seen);
        $fdisplay(fh, "  \"expected_events\": %0d,", EXPECTED_EVENTS);
        $fdisplay(fh, "  \"accepted_byte_cycles\": %0d,", accepted_byte_cycles);
        $fdisplay(fh, "  \"total_cycles\": %0d,", total_cycles);
        $fdisplay(fh, "  \"clock_period_ns\": %0d,", CLOCK_PERIOD_NS);
        $fdisplay(fh, "  \"failures\": %0d", failures);
        $fdisplay(fh, "}");
        $fclose(fh);
      end
    end
  endtask

  task automatic compare_event(input int index);
    logic [PACKED_EVENT_BITS-1:0] actual;
    begin
      actual = packed_actual_event();
      if (actual !== expected_events[index]) begin
        failures++;
        $display("ERROR: event %0d mismatch", index);
        $display("  actual   = %0h", actual);
        $display("  expected = %0h", expected_events[index]);
      end
    end
  endtask

  initial begin
    if (STREAM_BYTES <= 0 || STREAM_BYTES > MAX_BYTES) begin
      $fatal(1, "STREAM_BYTES must be in range 1..%0d, got %0d", MAX_BYTES, STREAM_BYTES);
    end
    if (EXPECTED_EVENTS <= 0 || EXPECTED_EVENTS > MAX_EVENTS) begin
      $fatal(1, "EXPECTED_EVENTS must be in range 1..%0d, got %0d", MAX_EVENTS, EXPECTED_EVENTS);
    end

    $readmemh("stream.mem", stream_mem, 0, STREAM_BYTES - 1);
    $readmemh("expected_events.mem", expected_events, 0, EXPECTED_EVENTS - 1);

    rst_n = 1'b0;
    evt_ready = 1'b0;
    s_axis_tvalid = 1'b0;
    s_axis_tdata = 8'd0;
    s_axis_tlast = 1'b0;

    byte_index = 0;
    bytes_accepted = 0;
    accepted_byte_cycles = 0;
    events_seen = 0;
    total_cycles = 0;
    cycle_count = 0;
    failures = 0;
    started = 1'b0;
    max_cycles = (STREAM_BYTES * 8) + (EXPECTED_EVENTS * 20) + 1000;

    // Vivado netlist simulations include glbl.GSR for roughly 100 ns.
    repeat (20) @(posedge clk);
    rst_n = 1'b1;
    repeat (2) @(posedge clk);

    while (events_seen < EXPECTED_EVENTS && cycle_count < max_cycles) begin
      bit input_stall;
      bit output_stall;
      bit will_accept;
      bit will_emit;

      @(negedge clk);
      input_stall = should_stall(INPUT_STALL_PERIOD, cycle_count);
      output_stall = should_stall(OUTPUT_STALL_PERIOD, cycle_count);

      s_axis_tvalid = (byte_index < STREAM_BYTES) && !input_stall;
      s_axis_tdata = (byte_index < STREAM_BYTES) ? stream_mem[byte_index] : 8'd0;
      s_axis_tlast = 1'b0;
      evt_ready = !output_stall;

      will_accept = s_axis_tvalid && s_axis_tready;
      will_emit = evt_valid && evt_ready;

      @(posedge clk);
      #1;

      if (will_accept) begin
        byte_index++;
        bytes_accepted++;
        accepted_byte_cycles++;
        started = 1'b1;
      end

      if (started) begin
        total_cycles++;
      end

      if (error_valid) begin
        failures++;
        $display("ERROR: DUT error_valid asserted with code %0d", error_code);
      end

      if (will_emit) begin
        if (VERIFY_EVENTS) begin
          compare_event(events_seen);
        end
        events_seen++;
      end

      cycle_count++;
    end

    s_axis_tvalid = 1'b0;
    evt_ready = 1'b0;

    if (cycle_count >= max_cycles) begin
      failures++;
      $display("ERROR: simulation timed out after %0d cycles", cycle_count);
    end
    if (bytes_accepted != STREAM_BYTES) begin
      failures++;
      $display("ERROR: accepted %0d bytes, expected %0d", bytes_accepted, STREAM_BYTES);
    end
    if (events_seen != EXPECTED_EVENTS) begin
      failures++;
      $display("ERROR: emitted %0d events, expected %0d", events_seen, EXPECTED_EVENTS);
    end

    write_result(failures == 0);
    if (failures == 0) begin
      $display(
          "PASS: xsim ITCH parser accepted %0d bytes, emitted %0d events in %0d cycles",
          bytes_accepted,
          events_seen,
          total_cycles
      );
      $finish;
    end

    $fatal(1, "FAIL: xsim ITCH parser saw %0d failures", failures);
  end

endmodule
