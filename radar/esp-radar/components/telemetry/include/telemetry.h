#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "radar_proto.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Producer/consumer telemetry.
 *
 *   producers (any core, never block)          consumer (core 1)
 *   CSI callback, STAT, logs, bench  --ring-->  transport task --> USB / UART
 *
 * Producers reserve space directly inside a FreeRTOS no-split ring buffer and
 * fill it in place. If the ring is full the record is dropped *and counted*;
 * nothing waits for the link. The transport task assigns the link sequence
 * number, appends the CRC and writes to the sink, so CRC cost and link stalls
 * stay off the acquisition core.
 */

typedef void (*telemetry_cmd_handler_t)(const char *line);

esp_err_t telemetry_init(void);

/* Reserve a packet with payload_len bytes. Returns a pointer to the payload,
 * or NULL if the ring is full (caller must count the drop). Never blocks. */
void *telemetry_reserve(uint8_t type, uint16_t payload_len, uint64_t t_us);
void telemetry_commit(void *payload);

/* Copying helpers for control packets; drops are counted in ctrl_drops. */
bool telemetry_send(uint8_t type, const void *payload, uint16_t len);
bool telemetry_text(uint8_t type, const char *fmt, ...) __attribute__((format(printf, 2, 3)));

esp_err_t telemetry_start_cmd_reader(telemetry_cmd_handler_t handler);

esp_err_t telemetry_set_data_sink(radar_sink_t sink);
radar_sink_t telemetry_data_sink(void);
const char *telemetry_sink_name(radar_sink_t sink);
void telemetry_use_psram_ring(bool psram);
/* Moves the transport task to another core (takes effect between packets). */
void telemetry_set_transport_core(int core);

/* Transport benchmark: BENCH packets (clearly typed, never CSI) at pps packets/s
 * of size bytes. pps = 0 means as fast as the ring accepts. size = 0 stops. */
void telemetry_bench(uint32_t pps, uint16_t size);

/* Fills the ring/transport/bench fields of a STAT and resets interval maxima. */
void telemetry_fill_stat(radar_stat_t *st);

/* Reboots into the ROM serial bootloader over USB (needed for TinyUSB builds). */
void telemetry_reboot_to_download(void);

#ifdef __cplusplus
}
#endif
