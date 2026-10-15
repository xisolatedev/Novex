/*
 * esp-radar-tx: controlled CSI source for the esp-radar S3 receiver.
 *
 * Broadcasts fixed-size ESP-NOW frames at a fixed rate on a fixed channel,
 * sent as HT20 MCS0 (OFDM) so the receiver gets L-LTF + HT-LTF CSI. The
 * default ESP-NOW rate is 1 Mbps DSSS, which produces no CSI at all.
 * No access point is involved.
 */
#include <inttypes.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

static const char *TAG = "radar-tx";

#define TX_MAGIC 0x58544452u  /* "RDTX" */

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint32_t tx_seq;       /* increments every scheduled packet, even if the send fails */
    uint64_t t_us;         /* esp_timer on the C6 when queued */
    uint16_t rate_hz;
    uint8_t  channel;
    uint8_t  reserved;
} tx_payload_hdr_t;

static const uint8_t BCAST[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
static TaskHandle_t s_tx_task;
static volatile uint32_t s_sent, s_send_err, s_cb_ok, s_cb_fail, s_late;

static void on_sent(const esp_now_send_info_t *info, esp_now_send_status_t status)
{
    if (status == ESP_NOW_SEND_SUCCESS) {
        s_cb_ok++;
    } else {
        s_cb_fail++;
    }
}

static void on_tick(void *arg)
{
    BaseType_t woken = pdFALSE;
    vTaskNotifyGiveFromISR(s_tx_task, &woken);
}

static void tx_task(void *arg)
{
    static uint8_t buf[CONFIG_TX_PAYLOAD_LEN];
    tx_payload_hdr_t *h = (tx_payload_hdr_t *)buf;
    for (size_t i = sizeof(*h); i < sizeof(buf); i++) {
        buf[i] = (uint8_t)i;
    }
    h->magic = TX_MAGIC;
    h->rate_hz = CONFIG_TX_RATE_HZ;
    h->channel = CONFIG_TX_CHANNEL;
    uint32_t seq = 0;
    for (;;) {
        uint32_t pending = ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (pending > 1) {
            s_late += pending - 1;   /* ticks we could not serve in time: counted, not hidden */
            seq += pending - 1;
        }
        h->tx_seq = seq++;
        h->t_us = esp_timer_get_time();
        esp_err_t err = esp_now_send(BCAST, buf, sizeof(buf));
        if (err == ESP_OK) {
            s_sent++;
        } else {
            s_send_err++;
            if (s_send_err < 5) {
                ESP_LOGE(TAG, "esp_now_send: %s", esp_err_to_name(err));
            }
        }
    }
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_TX_CHANNEL, WIFI_SECOND_CHAN_NONE));

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_register_send_cb(on_sent));
    esp_now_peer_info_t peer = {
        .channel = CONFIG_TX_CHANNEL,
        .ifidx = WIFI_IF_STA,
        .encrypt = false,
    };
    memcpy(peer.peer_addr, BCAST, 6);
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    esp_now_rate_config_t rate = {
        .phymode = WIFI_PHY_MODE_HT20,
        .rate = WIFI_PHY_RATE_MCS0_LGI,
        .ersu = false,
        .dcm = false,
    };
    err = esp_now_set_peer_rate_config(BCAST, &rate);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_now_set_peer_rate_config(HT20 MCS0) failed: %s -- frames would be DSSS (no CSI)",
                 esp_err_to_name(err));
    }

    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    ESP_LOGI(TAG, "TX MAC " MACSTR "  channel %d  %d Hz  payload %d B  PHY HT20 MCS0 (OFDM)",
             MAC2STR(mac), CONFIG_TX_CHANNEL, CONFIG_TX_RATE_HZ, CONFIG_TX_PAYLOAD_LEN);
    ESP_LOGI(TAG, "on the S3: ch %d, then mac " MACSTR, CONFIG_TX_CHANNEL, MAC2STR(mac));

    xTaskCreate(tx_task, "tx", 4096, NULL, 10, &s_tx_task);
    const esp_timer_create_args_t targs = { .callback = on_tick, .dispatch_method = ESP_TIMER_ISR,
                                            .name = "tx_tick" };
    esp_timer_handle_t timer;
    ESP_ERROR_CHECK(esp_timer_create(&targs, &timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(timer, 1000000 / CONFIG_TX_RATE_HZ));

    uint32_t prev = 0;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        uint32_t sent = s_sent;
        ESP_LOGI(TAG, "MAC " MACSTR " ch %d | %" PRIu32 " pkt/s | total sent %" PRIu32 " send_err %" PRIu32
                 " cb_ok %" PRIu32 " cb_fail %" PRIu32 " late %" PRIu32,
                 MAC2STR(mac), CONFIG_TX_CHANNEL, sent - prev, sent, s_send_err, s_cb_ok, s_cb_fail, s_late);
        prev = sent;
    }
}
