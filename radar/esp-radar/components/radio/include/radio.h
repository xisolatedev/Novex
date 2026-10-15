#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Brings Wi-Fi up in STA mode (not associated), power save off. */
esp_err_t radio_init(void);

/* Blocking all-channel scan. Emits one "AP,..." telemetry line per result.
 * Returns the primary channel of the strongest AP, or 0 if none were found.
 * Promiscuous mode is suspended during the scan and the current channel is
 * restored afterwards. */
uint8_t radio_scan_report(void);

/* Enables promiscuous RX. include_data=false captures management frames only. */
esp_err_t radio_promisc_start(bool include_data);
esp_err_t radio_set_promisc_data(bool include_data);
bool radio_promisc_data(void);

esp_err_t radio_set_channel(uint8_t channel);
uint8_t radio_channel(void);

#ifdef __cplusplus
}
#endif
