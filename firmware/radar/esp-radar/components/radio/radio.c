#include "radio.h"

#include <string.h>
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "telemetry.h"

static const char *TAG = "radio";

#define MAX_SCAN_RESULTS 32

static uint8_t s_channel = 1;
static bool s_promisc_on;
static bool s_promisc_data;

esp_err_t radio_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition needs erase (%s)", esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_flash_init failed: %s", esp_err_to_name(err));
        return err;
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_init failed: %s", esp_err_to_name(err));
        return err;
    }
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Modem sleep drops most frames between DTIM beacons; CSI needs the radio awake. */
    err = esp_wifi_set_ps(WIFI_PS_NONE);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_ps(NONE) failed: %s", esp_err_to_name(err));
    }

    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    ESP_LOGI(TAG, "Wi-Fi started in STA mode (unassociated), MAC " MACSTR ", power save off",
             MAC2STR(mac));
    return ESP_OK;
}

static const char *auth_name(wifi_auth_mode_t m)
{
    switch (m) {
    case WIFI_AUTH_OPEN: return "open";
    case WIFI_AUTH_WEP: return "wep";
    case WIFI_AUTH_WPA_PSK: return "wpa";
    case WIFI_AUTH_WPA2_PSK: return "wpa2";
    case WIFI_AUTH_WPA_WPA2_PSK: return "wpa/wpa2";
    case WIFI_AUTH_WPA3_PSK: return "wpa3";
    case WIFI_AUTH_WPA2_WPA3_PSK: return "wpa2/wpa3";
    default: return "other";
    }
}

uint8_t radio_scan_report(void)
{
    bool was_promisc = s_promisc_on;
    if (was_promisc) {
        esp_wifi_set_promiscuous(false);
    }

    ESP_LOGI(TAG, "Scanning all channels...");
    wifi_scan_config_t sc = { .show_hidden = true };
    esp_err_t err = esp_wifi_scan_start(&sc, true);
    uint8_t best_ch = 0;
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_scan_start failed: %s", esp_err_to_name(err));
    } else {
        uint16_t n = MAX_SCAN_RESULTS;
        static wifi_ap_record_t recs[MAX_SCAN_RESULTS];
        err = esp_wifi_scan_get_ap_records(&n, recs);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "esp_wifi_scan_get_ap_records failed: %s", esp_err_to_name(err));
            n = 0;
        }
        ESP_LOGI(TAG, "Scan found %u APs", n);
        int8_t best_rssi = -128;
        for (int i = 0; i < n; i++) {
            const wifi_ap_record_t *r = &recs[i];
            /* SSID last: it may contain commas. */
            telemetry_text(RADAR_PKT_AP, MACSTR ",%u,%d,%s,%s", MAC2STR(r->bssid), r->primary,
                             r->rssi, auth_name(r->authmode), (const char *)r->ssid);
            if (r->rssi > best_rssi) {
                best_rssi = r->rssi;
                best_ch = r->primary;
            }
        }
        telemetry_text(RADAR_PKT_REPLY, "APEND,%u", n);
    }

    if (was_promisc) {
        esp_wifi_set_promiscuous(true);
    }
    /* A scan leaves the radio on whatever channel it visited last. */
    radio_set_channel(s_channel);
    return best_ch;
}

static esp_err_t apply_filter(void)
{
    wifi_promiscuous_filter_t f = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT |
                       (s_promisc_data ? WIFI_PROMIS_FILTER_MASK_DATA : 0),
    };
    esp_err_t err = esp_wifi_set_promiscuous_filter(&f);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_promiscuous_filter failed: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "Promiscuous filter: %s", s_promisc_data ? "MGMT+DATA" : "MGMT only");
    }
    return err;
}

esp_err_t radio_promisc_start(bool include_data)
{
    s_promisc_data = include_data;
    esp_err_t err = apply_filter();
    if (err != ESP_OK) {
        return err;
    }
    err = esp_wifi_set_promiscuous(true);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_promiscuous(true) failed: %s", esp_err_to_name(err));
        return err;
    }
    s_promisc_on = true;
    ESP_LOGI(TAG, "Promiscuous mode on");
    return ESP_OK;
}

esp_err_t radio_set_promisc_data(bool include_data)
{
    s_promisc_data = include_data;
    return apply_filter();
}

bool radio_promisc_data(void)
{
    return s_promisc_data;
}

esp_err_t radio_set_channel(uint8_t channel)
{
    if (channel < 1 || channel > 13) {
        ESP_LOGE(TAG, "Invalid channel %u", channel);
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t err = esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_channel(%u) failed: %s", channel, esp_err_to_name(err));
        return err;
    }
    s_channel = channel;
    ESP_LOGI(TAG, "Channel set to %u (20 MHz, no secondary)", channel);
    return ESP_OK;
}

uint8_t radio_channel(void)
{
    return s_channel;
}
