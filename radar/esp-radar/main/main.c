/*
 * esp-radar: ESP32-S3 CSI acquisition node.
 *
 * Core 0: Wi-Fi task -> CSI callback -> ring buffer (zero-copy, never blocks)
 * Core 1: transport task -> CRC + link sequence -> native USB (binary)
 * UART0 (CH343, when connected): plain-text debug log channel.
 *
 * Future (not implemented yet): a DSP/TFLM task on core 1 consuming from its
 * own ring, so inference can never back-pressure acquisition.
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "sdkconfig.h"

#include "csi.h"
#include "radio.h"
#include "telemetry.h"

static const char *TAG = "main";

#define FW_VERSION "0.2.0"

static void send_hello(void)
{
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    uint32_t flash = 0;
    esp_flash_get_size(NULL, &flash);
    uint8_t mac[6] = {0};
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    uint8_t fmac[6];
    char filter[18] = "any";
    if (csi_get_mac_filter(fmac)) {
        snprintf(filter, sizeof(filter), MACSTR, MAC2STR(fmac));
    }
    telemetry_text(RADAR_PKT_HELLO,
                   "fw=esp-radar,version=%s,target=%s,rev=%d.%d,cores=%d,flash_mb=%" PRIu32
                   ",psram=%u,mac=" MACSTR ",ch=%u,filter=%s,promisc=%s,csi=%s,sink=%s,proto=%d",
                   FW_VERSION, CONFIG_IDF_TARGET, chip.revision / 100, chip.revision % 100,
                   chip.cores, flash / (1024 * 1024),
                   (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM), MAC2STR(mac),
                   radio_channel(), filter, radio_promisc_data() ? "all" : "mgmt",
                   csi_enabled() ? "on" : "off", telemetry_sink_name(telemetry_data_sink()),
                   RADAR_PROTO_VER);
}

static bool parse_mac(const char *s, uint8_t out[6])
{
    unsigned v[6];
    if (sscanf(s, "%x:%x:%x:%x:%x:%x", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5]) != 6) {
        return false;
    }
    for (int i = 0; i < 6; i++) {
        out[i] = (uint8_t)v[i];
    }
    return true;
}

static void cmd_top(void);

#define ACK(...) telemetry_text(RADAR_PKT_REPLY, "ACK," __VA_ARGS__)
#define ERR(...) telemetry_text(RADAR_PKT_REPLY, "ERR," __VA_ARGS__)

/* Host commands, one text line each:
 *   ch <1-13> | mac <aa:bb:cc:dd:ee:ff|any> | filter <mgmt|all> | csi <on|off>
 *   scan | info | ping <token>
 *   sink <usb|uart|uart-text> | ring <int|psram>
 *   bench <pps> <bytes> | bench off | bootloader */
static void handle_cmd(const char *line)
{
    char cmd[16] = {0};
    char arg[64] = {0};
    char arg2[32] = {0};
    sscanf(line, "%15s %63s %31s", cmd, arg, arg2);

    if (strcmp(cmd, "ping") == 0) {
        radar_pong_t p = { .pc_token = strtoull(arg, NULL, 10), .esp_us = esp_timer_get_time() };
        telemetry_send(RADAR_PKT_PONG, &p, sizeof(p));
        return;
    }
    ESP_LOGI(TAG, "cmd: '%s'", line);
    if (strcmp(cmd, "ch") == 0) {
        int ch = atoi(arg);
        if (radio_set_channel(ch) == ESP_OK) {
            ACK("ch,%d", ch);
        } else {
            ERR("ch,invalid channel '%s'", arg);
        }
    } else if (strcmp(cmd, "mac") == 0) {
        uint8_t mac[6];
        if (strcmp(arg, "any") == 0) {
            csi_set_mac_filter(NULL);
            ACK("mac,any");
        } else if (parse_mac(arg, mac)) {
            csi_set_mac_filter(mac);
            ACK("mac,%s", arg);
        } else {
            ERR("mac,bad address '%s'", arg);
        }
    } else if (strcmp(cmd, "filter") == 0) {
        if (strcmp(arg, "mgmt") == 0 || strcmp(arg, "all") == 0) {
            radio_set_promisc_data(strcmp(arg, "all") == 0);
            ACK("filter,%s", arg);
        } else {
            ERR("filter,expected mgmt|all");
        }
    } else if (strcmp(cmd, "csi") == 0) {
        csi_enable(strcmp(arg, "off") != 0);
        ACK("csi,%s", csi_enabled() ? "on" : "off");
    } else if (strcmp(cmd, "scan") == 0) {
        radio_scan_report();
        ACK("scan");
    } else if (strcmp(cmd, "info") == 0) {
        send_hello();
    } else if (strcmp(cmd, "sink") == 0) {
        radar_sink_t s;
        if (strcmp(arg, "usb") == 0) {
#if CONFIG_RADAR_USB_TINYUSB
            s = RADAR_SINK_TINYUSB;
#else
            s = RADAR_SINK_USB_JTAG;
#endif
        } else if (strcmp(arg, "uart") == 0) {
            s = RADAR_SINK_UART_BIN;
        } else if (strcmp(arg, "uart-text") == 0) {
            s = RADAR_SINK_UART_TXT;
        } else {
            ERR("sink,expected usb|uart|uart-text");
            return;
        }
        if (telemetry_set_data_sink(s) == ESP_OK) {
            ACK("sink,%s", telemetry_sink_name(s));
        } else {
            ERR("sink,not available in this build");
        }
    } else if (strcmp(cmd, "ring") == 0) {
        telemetry_use_psram_ring(strcmp(arg, "psram") == 0);
        ACK("ring,%s", arg);
    } else if (strcmp(cmd, "bench") == 0) {
        if (strcmp(arg, "off") == 0) {
            telemetry_bench(0, 0);
        } else {
            telemetry_bench(strtoul(arg, NULL, 10), (uint16_t)strtoul(arg2, NULL, 10));
        }
        ACK("bench,%s,%s", arg, arg2);
    } else if (strcmp(cmd, "tcore") == 0) {
        telemetry_set_transport_core(atoi(arg));
        ACK("tcore,%d", atoi(arg) ? 1 : 0);
    } else if (strcmp(cmd, "top") == 0) {
        cmd_top();
    } else if (strcmp(cmd, "bootloader") == 0) {
        ACK("bootloader");
        telemetry_reboot_to_download();
    } else {
        ERR("unknown command '%s'", line);
    }
}

/* "top": per-task CPU share since the previous "top", one LOG line per task. */
static void cmd_top(void)
{
    enum { MAX_TASKS = 40 };
    static TaskStatus_t prev[MAX_TASKS];
    static UBaseType_t n_prev;
    static uint32_t t_prev;
    static TaskStatus_t cur[MAX_TASKS];
    uint32_t total = 0;
    UBaseType_t n = uxTaskGetSystemState(cur, MAX_TASKS, &total);
    uint32_t dt = total - t_prev;
    for (UBaseType_t i = 0; i < n && dt; i++) {
        uint32_t before = 0;
        for (UBaseType_t j = 0; j < n_prev; j++) {
            if (prev[j].xHandle == cur[i].xHandle) {
                before = prev[j].ulRunTimeCounter;
                break;
            }
        }
        uint32_t d = cur[i].ulRunTimeCounter - before;
        if (d * 1000ULL / dt >= 1) {   /* hide tasks under 0.1 % */
            BaseType_t core = xTaskGetCoreID(cur[i].xHandle);
            ESP_LOGI(TAG, "top %-12s core %s prio %2u  %5.1f %%", cur[i].pcTaskName,
                     core == tskNO_AFFINITY ? "any" : (core ? "1" : "0"),
                     (unsigned)cur[i].uxCurrentPriority, d * 100.0 / dt);
        }
    }
    ESP_LOGI(TAG, "top window %.2f s (per-task %% of one core)", dt / 1e6);
    memcpy(prev, cur, sizeof(TaskStatus_t) * n);
    n_prev = n;
    t_prev = total;
}

/* Busy fraction per core from the idle tasks' run-time counters. */
static void cpu_load(uint16_t out_permille[2])
{
    static uint32_t prev_idle[2];
    static int64_t prev_t;
    int64_t now = esp_timer_get_time();
    uint32_t dt = (uint32_t)(now - prev_t);
    for (int c = 0; c < 2; c++) {
        uint32_t idle = ulTaskGetIdleRunTimeCounterForCore(c);
        uint32_t d = idle - prev_idle[c];
        prev_idle[c] = idle;
        out_permille[c] = (prev_t && dt) ? (uint16_t)(d >= dt ? 0 : 1000 - (uint64_t)d * 1000 / dt) : 0;
    }
    prev_t = now;
}

void app_main(void)
{
    ESP_ERROR_CHECK(telemetry_init());
    ESP_LOGI(TAG, "esp-radar %s starting (IDF %s)", FW_VERSION, esp_get_idf_version());

    ESP_ERROR_CHECK(radio_init());
    uint8_t best = radio_scan_report();
    uint8_t ch = CONFIG_RADAR_CSI_CHANNEL;
    if (ch == 0) {
        if (best != 0) {
            ch = best;
            ESP_LOGI(TAG, "Auto channel: %u (strongest AP)", ch);
        } else {
            ch = 6;
            ESP_LOGW(TAG, "No APs found, falling back to channel %u", ch);
        }
    }
    ESP_ERROR_CHECK(radio_set_channel(ch));
    ESP_ERROR_CHECK(radio_promisc_start(CONFIG_RADAR_PROMISC_DATA));
    ESP_ERROR_CHECK(csi_init());
    ESP_ERROR_CHECK(telemetry_start_cmd_reader(handle_cmd));
    send_hello();

    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(1000));
        csi_stats_t cs;
        csi_get_stats(&cs);
        radar_stat_t st = {0};
        st.uptime_ms = (uint32_t)(esp_timer_get_time() / 1000);
        st.csi_callbacks = cs.callbacks;
        st.csi_filtered = cs.filtered;
        st.csi_accepted = cs.accepted;
        st.csi_ring_drops = cs.ring_drops;
        st.csi_truncated = cs.truncated;
        st.cb_us_max = cs.cb_us_max;
        st.cb_us_sum = cs.cb_us_sum;
        st.channel = radio_channel();
        st.promisc_data = radio_promisc_data();
        telemetry_fill_stat(&st);
        uint16_t cpu[2];
        cpu_load(cpu);
        st.cpu0_permille = cpu[0];
        st.cpu1_permille = cpu[1];
        st.heap_int_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
        st.heap_int_min = heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL);
        st.heap_int_largest = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL);
        st.psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        st.psram_total = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
        telemetry_send(RADAR_PKT_STAT, &st, sizeof(st));
    }
}
