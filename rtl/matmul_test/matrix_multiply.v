`timescale 1ns / 1ps

/* 
----------------------------------------------------------------------------------
--	(c) Rajesh C Panicker, NUS
--  Description : Template for the Matrix Multiply unit for the AXI Stream Coprocessor
--	License terms :
--	You are free to use this code as long as you
--		(i) DO NOT post a modified version of this on any public repository;
--		(ii) use it only for educational purposes;
--		(iii) accept the responsibility to ensure that your implementation does not violate any intellectual property of any entity.
--		(iv) accept that the program is provided "as is" without warranty of any kind or assurance regarding its suitability for any particular purpose;
--		(v) send an email to rajesh.panicker@ieee.org briefly mentioning its use (except when used for the course EE4218 at the National University of Singapore);
--		(vi) retain this notice in this file or any files derived from this.
----------------------------------------------------------------------------------
*/

/* Implemented by Chen Shimin */

// those outputs which are assigned in an always block of matrix_multiply shoud be changes to reg (such as output reg Done).

module matrix_multiply
	#(	parameter width = 8, 			// width is the number of bits per location
		parameter A_depth_bits = 3, 	// depth is the number of locations (2^number of address bits)
		parameter B_depth_bits = 2,
		parameter A_len = 8,			// 2^A
		parameter B_len = 4,			// 2^B
		parameter RES_depth_bits = 1
		// (n,m) * (m,1) = (n,1)
		// n*m = 2^A, m = 2^B => n = 2^(A-B)
	) 
	(
		input clk,										
		input Start,									// myip_v1_0 -> matrix_multiply_0.
		output reg Done,									// matrix_multiply_0 -> myip_v1_0. Possibly reg.
		
		output reg A_read_en,  								// matrix_multiply_0 -> A_RAM. Possibly reg.
		output reg [A_depth_bits-1:0] A_read_address, 		// matrix_multiply_0 -> A_RAM. Possibly reg.
		input [width-1:0] A_read_data_out,				// A_RAM -> matrix_multiply_0.
		
		output reg B_read_en, 								// matrix_multiply_0 -> B_RAM. Possibly reg.
		output reg [B_depth_bits-1:0] B_read_address, 		// matrix_multiply_0 -> B_RAM. Possibly reg.
		input [width-1:0] B_read_data_out,				// B_RAM -> matrix_multiply_0.
		
		output reg RES_write_en, 							// matrix_multiply_0 -> RES_RAM. Possibly reg.
		output reg [A_depth_bits-B_depth_bits-1:0] RES_write_address, 	// matrix_multiply_0 -> RES_RAM. Possibly reg.
		output reg [width-1:0] RES_write_data_in 			// matrix_multiply_0 -> RES_RAM. Possibly reg.
	);
	
	// implement the logic to read A_RAM, read B_RAM, do the multiplication and write the results to RES_RAM
	// Note: A_RAM and B_RAM are to be read synchronously. Read the wiki for more details.
	
	reg init;
	reg [2*width-1:0] tmp_res;
	wire [2*width-1:0] nxt_tmp_res;
	reg begin_new_line;
	reg increase_RES_addr;
	reg read_end;
	
	wire [A_depth_bits-1:0] A_nxt_address;
	wire [B_depth_bits-1:0] B_nxt_address;
	wire [A_depth_bits-B_depth_bits-1:0] RES_nxt_address;
	
	assign A_nxt_address	= A_read_address + 1;
	assign B_nxt_address	= B_read_address + 1;
	assign nxt_tmp_res = tmp_res + A_read_data_out * B_read_data_out;

	// assign Done = Start; // dummy code. Change as appropriate.
	always @(posedge clk) 
	begin
		if (Start) begin
			RES_write_en <= 0; // default: do not write
			if (init) begin
				// initialization
				A_read_en			<= 1;
				B_read_en			<= 1;
				A_read_address		<= 0;
				B_read_address		<= 0;
				RES_write_address	<= 0;
				tmp_res				<= 0;
				begin_new_line		<= 0;
				increase_RES_addr	<= 0;
				read_end			<= 0;
				Done				<= 0;
				init				<= 0;
			end else begin
				if (read_end) begin
					A_read_en			<= 0;
					B_read_en			<= 0;
				end else begin
					A_read_address		<= A_nxt_address;
					B_read_address		<= B_nxt_address;
					read_end 			<= A_nxt_address == 0;
				end
				if (A_nxt_address >= 2 || A_nxt_address == 0) // when A B outputs are available
					tmp_res				<= nxt_tmp_res;
				if (increase_RES_addr) begin
					RES_write_address 	<= RES_write_address + 1;
					increase_RES_addr	<= 0;
					Done				<= read_end;
				end
				if (begin_new_line) begin
					// STORE THE TMP_RES
					RES_write_en 		<= 1;
					RES_write_data_in 	<= nxt_tmp_res[2*width-1:width];
					increase_RES_addr	<= 1;
					tmp_res				<= 0;
					begin_new_line		<= 0;
				end
				begin_new_line		<= B_nxt_address == 0; // when overflow
			end
		end else begin
			// Idle state. keep init high
			init <= 1;
			Done <= 0;
		end
	end

endmodule


