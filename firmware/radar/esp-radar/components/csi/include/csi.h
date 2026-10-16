#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t callbacks;   /* every CSI callback from the Wi-Fi driver */
    uint32_t filtered;    /* rejected by the source-MAC filter */
    uint32_t accepted;    /* passed the filter, got a frame_id */
    uint32_t ring_drops;  /* accepted but the ring was full: dropped and counted */
    uint32_t truncated;   /* CSI longer than RADAR_CSI_MAX_LEN, clipped */
    uint32_t cb_us_max;   /* callback duration since last csi_get_stats() */
    uint32_t cb_us_sum;
} csi_stats_t;

/* Configures the CSI engine (raw, unsmoothed subcarriers). Wi-Fi must be
 * started and telemetry initialised. */
esp_err_t csi_init(void);

esp_err_t csi_enable(bool on);
bool csi_enabled(void);

/* Only forward CSI whose source MAC matches. NULL clears the filter. */
void csi_set_mac_filter(const uint8_t mac[6]);
bool csi_get_mac_filter(uint8_t mac_out[6]);

/* Snapshot of the counters; resets the per-interval callback timing. */
void csi_get_stats(csi_stats_t *out);

#ifdef __cplusplus
}
#endif
