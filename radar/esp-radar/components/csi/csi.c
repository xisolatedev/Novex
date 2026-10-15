#include "csi.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "esp_cpu.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "telemetry.h"

static const char *TAG = "csi";

static volatile bool s_enabled;
static volatile bool s_filter_on;
static uint8_t s_filter_mac[6];
static csi_stats_t s_stats;
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;

/* Runs in the Wi-Fi task (core 0). Writes the binary record straight into the
 * ring; never waits for the link. */
static void csi_rx_cb(void *ctx, wifi_csi_info_t *info)
{
    uint32_t c0 = esp_cpu_get_cycle_count();
    uint64_t t_us = esp_timer_get_time();
    s_stats.callbacks++;
    if (!s_enabled || info == NULL || info->buf == NULL) {
        return;
    }
    if (s_filter_on && memcmp(info->mac, s_filter_mac, 6) != 0) {
        s_stats.filtered++;
        return;
    }

    uint16_t len = info->len;
    uint8_t flags = info->first_word_invalid ? 1 : 0;
    if (len > RADAR_CSI_MAX_LEN) {
        len = RADAR_CSI_MAX_LEN;
        flags |= 2;
        s_stats.truncated++;
    }
    uint32_t frame_id = s_stats.accepted++;
    radar_csi_t *c = telemetry_reserve(RADAR_PKT_CSI, sizeof(radar_csi_t) + len, t_us);
    if (c == NULL) {
        s_stats.ring_drops++;
    } else {
        const wifi_pkt_rx_ctrl_t *rx = &info->rx_ctrl;
        c->frame_id = frame_id;
        c->rx_us = rx->timestamp;
        memcpy(c->src, info->mac, 6);
        memcpy(c->dst, info->dmac, 6);
        c->rssi = rx->rssi;
        c->noise_floor = rx->noise_floor;
        c->channel = rx->channel;
        c->secondary = rx->secondary_channel;
        c->sig_mode = rx->sig_mode;
        c->mcs = rx->mcs;
        c->cwb = rx->cwb;
        c->stbc = rx->stbc;
        c->rate = rx->rate;
        c->flags = flags;
        c->rx_seq = info->rx_seq;
        c->orig_len = info->len;
        c->csi_len = len;
        memcpy(c + 1, info->buf, len);
        telemetry_commit(c);
    }

    uint32_t us = (esp_cpu_get_cycle_count() - c0) / (CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ);
    s_stats.cb_us_sum += us;
    if (us > s_stats.cb_us_max) {
        s_stats.cb_us_max = us;
    }
}

esp_err_t csi_init(void)
{
    /* ESP32-S3 (802.11n, no HE): legacy CSI config. Raw subcarriers, no smoothing. */
    wifi_csi_config_t cfg = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = true,
        .ltf_merge_en = true,
        .channel_filter_en = false,
        .manu_scale = false,
        .shift = 0,
        .dump_ack_en = false,
    };
    esp_err_t err = esp_wifi_set_csi_config(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_csi_config failed: %s", esp_err_to_name(err));
        return err;
    }
    err = esp_wifi_set_csi_rx_cb(csi_rx_cb, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_csi_rx_cb failed: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "CSI configured: LLTF+HTLTF+STBC, channel filter OFF, auto scale, "
             "zero-copy into telemetry ring");
    return csi_enable(true);
}

esp_err_t csi_enable(bool on)
{
    s_enabled = on;
    esp_err_t err = esp_wifi_set_csi(on);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_csi(%d) failed: %s", on, esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "CSI %s", on ? "enabled" : "disabled");
    }
    return err;
}

bool csi_enabled(void)
{
    return s_enabled;
}

void csi_set_mac_filter(const uint8_t mac[6])
{
    taskENTER_CRITICAL(&s_lock);
    if (mac) {
        memcpy(s_filter_mac, mac, 6);
        s_filter_on = true;
    } else {
        s_filter_on = false;
    }
    taskEXIT_CRITICAL(&s_lock);
    if (mac) {
        ESP_LOGI(TAG, "MAC filter: %02x:%02x:%02x:%02x:%02x:%02x",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    } else {
        ESP_LOGI(TAG, "MAC filter cleared (all sources)");
    }
}

bool csi_get_mac_filter(uint8_t mac_out[6])
{
    if (s_filter_on) {
        memcpy(mac_out, s_filter_mac, 6);
    }
    return s_filter_on;
}

void csi_get_stats(csi_stats_t *out)
{
    *out = s_stats;
    s_stats.cb_us_max = 0;
    s_stats.cb_us_sum = 0;
}
