/**************************************************************************/
/*  debug_transport_v2.h                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                             GODOT ENGINE                               */
/*                        https://godotengine.org                         */
/**************************************************************************/
/* Copyright (c) 2014-present Godot Engine contributors (see AUTHORS.md). */
/* Copyright (c) 2007-2014 Juan Linietsky, Ariel Manzur.                  */
/*                                                                        */
/* Permission is hereby granted, free of charge, to any person obtaining  */
/* a copy of this software and associated documentation files (the        */
/* "Software"), to deal in the Software without restriction, including  */
/* without limitation the rights to use, copy, modify, merge, publish,    */
/* distribute, sublicense, and/or sell copies of the Software, and to     */
/* permit persons to whom the Software is furnished to do so, subject to  */
/* the following conditions:                                              */
/*                                                                        */
/* The above copyright notice and this permission notice shall be         */
/* included in all copies or substantial portions of the Software.        */
/*                                                                        */
/* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,        */
/* EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF     */
/* MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. */
/* IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY   */
/* CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,   */
/* TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE      */
/* SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                 */
/**************************************************************************/

#ifndef DEBUG_TRANSPORT_V2_H
#define DEBUG_TRANSPORT_V2_H

#include "core/io/packet_peer.h"
#include "core/io/stream_peer_tcp.h"
#include "debug_protocol_v2.h"

class DebugTransportV2 {
	Ref<StreamPeerTCP> control_tcp;
	Ref<PacketPeerStream> control_peer;
	Ref<StreamPeerTCP> data_tcp;
	Ref<PacketPeerStream> data_peer;

	String reconnect_host;
	uint16_t reconnect_port = 0;
	uint64_t session_id = 0;
	uint32_t generation = 1;
	uint64_t control_sequence = 0;
	uint64_t data_sequence = 0;
	uint32_t heartbeat_interval_msec = 250;
	uint32_t heartbeat_timeout_msec = 1000;
	uint32_t variable_page_size = 100;

	static uint64_t _make_session_id();
	Error _wait_for_connections(uint32_t p_timeout_msec);
	Error _wait_for_hello_ack(DebugProtocolV2::Channel p_channel, uint32_t p_timeout_msec);
	Error _poll(Ref<PacketPeerStream> p_peer, DebugProtocolV2::Channel p_channel, DebugProtocolV2::Envelope &r_message);

public:
	Error connect_to_host(const String &p_host, uint16_t p_port, uint32_t p_timeout_msec = 5000);
	void disconnect();

	Error send_control(const String &p_type, const Array &p_payload = Array(), uint64_t p_request_id = 0, uint64_t p_stop_id = 0);
	Error send_data(const String &p_type, const Array &p_payload = Array(), uint64_t p_request_id = 0, uint64_t p_stop_id = 0);
	Error poll_control(DebugProtocolV2::Envelope &r_message);
	Error poll_data(DebugProtocolV2::Envelope &r_message);

	bool is_control_connected() const;
	bool is_data_connected() const;
	bool is_connected() const;

	uint64_t get_session_id() const { return session_id; }
	uint32_t get_generation() const { return generation; }
	uint32_t get_heartbeat_interval_msec() const { return heartbeat_interval_msec; }
	uint32_t get_heartbeat_timeout_msec() const { return heartbeat_timeout_msec; }
	uint32_t get_variable_page_size() const { return variable_page_size; }
	String get_reconnect_host() const { return reconnect_host; }
	uint16_t get_reconnect_port() const { return reconnect_port; }

	// Removed after all legacy debugger data messages are migrated in tasks 4-5.
	Ref<PacketPeerStream> get_legacy_data_peer() const { return data_peer; }

	DebugTransportV2();
};

#endif // DEBUG_TRANSPORT_V2_H
