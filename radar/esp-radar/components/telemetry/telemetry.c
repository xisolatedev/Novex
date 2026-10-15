#include "telemetry.h"

#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"
#include "freertos/task.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_rom_crc.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "driver/uart.h"
#include "sdkconfig.h"
#include "soc/rtc_cntl_reg.h"
#include "link_usb.h"

static const char *TAG = "telemetry";

#define UART_PORT       UART_NUM_0
#define UART_BAUD       2000000
#define UART_TX_BUF     (16 * 1024)
#define RING_INT_SIZE   (CONFIG_RADAR_RING_INT_KB * 1024)
#define RING_PSRAM_SIZE (CONFIG_RADAR_RING_PSRAM_KB * 1024)
#define CMD_MAX_LEN     128
#define PKT_OVERHEAD    (sizeof(radar_hdr_t) + RADAR_CRC_LEN)

enum { LINK_USB = 0, LINK_UART = 1 };

/* Data rings carry CSI/BENCH: [0] internal RAM, [1] PSRAM (runtime choice).
 * Control packets (STAT, LOG, replies) get their own small ring that the
 * transport drains first, so they still flow while data saturates the link. */
#define RING_CTRL       2
#define RING_CTRL_SIZE  (16 * 1024)
static RingbufHandle_t s_ring[3];
static size_t s_ring_size[3];
static volatile int s_active;             /* ring producers write to */
static volatile radar_sink_t s_sink = RADAR_SINK_USB_JTAG;
static telemetry_cmd_handler_t s_handler;
static uint32_t s_link_seq[2];

/* stats (single writer each, read by the STAT task; wait sum is per STAT interval) */
static volatile uint32_t s_tx_bytes, s_tx_pkts, s_tx_write_us;
static volatile uint32_t s_wait_max, s_wait_sum;
static uint32_t s_ctrl_drops;             /* many producers: atomic */
static volatile uint32_t s_link_drops;
static volatile uint32_t s_ring_free_min = UINT32_MAX;
static volatile uint32_t s_bench_generated, s_bench_drops;
static volatile uint32_t s_bench_pps;
static volatile int s_transport_core = CONFIG_RADAR_TRANSPORT_CORE;
static volatile uint16_t s_bench_size;

const char *telemetry_sink_name(radar_sink_t sink)
{
    switch (sink) {
    case RADAR_SINK_USB_JTAG: return "usb-jtag";
    case RADAR_SINK_UART_BIN: return "uart-bin";
    case RADAR_SINK_UART_TXT: return "uart-text";
    case RADAR_SINK_TINYUSB: return "tinyusb-cdc";
    default: return "?";
    }
}

static radar_sink_t usb_sink(void)
{
    return link_usb_is_tinyusb() ? RADAR_SINK_TINYUSB : RADAR_SINK_USB_JTAG;
}

/* ---------------- producer side ---------------- */

void *telemetry_reserve(uint8_t type, uint16_t payload_len, uint64_t t_us)
{
    bool is_data = type == RADAR_PKT_CSI || type == RADAR_PKT_BENCH;
    int r = is_data ? s_active : RING_CTRL;
    void *item = NULL;
    if (xRingbufferSendAcquire(s_ring[r], &item, PKT_OVERHEAD + payload_len, 0) != pdTRUE) {
        return NULL;
    }
    radar_hdr_t *h = item;
    h->sync[0] = RADAR_SYNC0;
    h->sync[1] = RADAR_SYNC1;
    h->version = RADAR_PROTO_VER;
    h->type = type;
    h->payload_len = payload_len;
    h->flags = r; /* commit needs to know which ring owns the item */
    h->seq = 0;
    h->t_us = t_us;
    return h + 1;
}

void telemetry_commit(void *payload)
{
    radar_hdr_t *h = (radar_hdr_t *)payload - 1;
    int r = h->flags;
    xRingbufferSendComplete(s_ring[r], h);
    if (r == RING_CTRL) {
        return;
    }
    size_t free_now = xRingbufferGetCurFreeSize(s_ring[r]);
    if (free_now < s_ring_free_min) {
        s_ring_free_min = free_now;
    }
}

bool telemetry_send(uint8_t type, const void *payload, uint16_t len)
{
    void *p = telemetry_reserve(type, len, esp_timer_get_time());
    if (p == NULL) {
        __atomic_fetch_add(&s_ctrl_drops, 1, __ATOMIC_RELAXED);
        return false;
    }
    memcpy(p, payload, len);
    telemetry_commit(p);
    return true;
}

static bool vtext(uint8_t type, const char *fmt, va_list ap)
{
    char buf[256];
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    if (n < 0) {
        return false;
    }
    if (n >= (int)sizeof(buf)) {
        n = sizeof(buf) - 1;
    }
    return telemetry_send(type, buf, n);
}

bool telemetry_text(uint8_t type, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    bool ok = vtext(type, fmt, ap);
    va_end(ap);
    return ok;
}

/* ESP_LOG -> LOG packets on the USB stream, plus plain text on UART0 as a
 * separate debug channel (unless UART0 is carrying the binary stream). */
static int log_hook(const char *fmt, va_list ap)
{
    char buf[256];
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    if (n <= 0) {
        return n;
    }
    if (n >= (int)sizeof(buf)) {
        n = sizeof(buf) - 1;
    }
    if (s_sink != RADAR_SINK_UART_BIN) {
        uart_write_bytes(UART_PORT, buf, n);
    }
    int len = n;
    while (len > 0 && (buf[len - 1] == '\n' || buf[len - 1] == '\r')) {
        len--;
    }
    if (len > 0) {
        telemetry_send(RADAR_PKT_LOG, buf, len);
    }
    return n;
}

/* ---------------- consumer side (core 1) ---------------- */

static void uart_write_paced(const void *buf, size_t len);

static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static size_t b64_encode(const uint8_t *in, size_t n, char *out)
{
    size_t o = 0, i = 0;
    for (; i + 2 < n; i += 3) {
        uint32_t v = (in[i] << 16) | (in[i + 1] << 8) | in[i + 2];
        out[o++] = B64[(v >> 18) & 63];
        out[o++] = B64[(v >> 12) & 63];
        out[o++] = B64[(v >> 6) & 63];
        out[o++] = B64[v & 63];
    }
    if (i < n) {
        uint32_t v = in[i] << 16;
        if (i + 1 < n) {
            v |= in[i + 1] << 8;
        }
        out[o++] = B64[(v >> 18) & 63];
        out[o++] = B64[(v >> 12) & 63];
        out[o++] = (i + 1 < n) ? B64[(v >> 6) & 63] : '=';
        out[o++] = '=';
    }
    return o;
}

/* v0.1 text line, kept only as the measured baseline (sink "uart-text"). */
static void write_csi_text(const radar_hdr_t *h)
{
    static char line[256 + (RADAR_CSI_MAX_LEN * 4) / 3 + 8];
    const radar_csi_t *c = (const radar_csi_t *)(h + 1);
    int n = snprintf(line, sizeof(line),
                     "CSI,%" PRIu32 ",%lld,%" PRIu32 ","
                     "%02x:%02x:%02x:%02x:%02x:%02x,%02x:%02x:%02x:%02x:%02x:%02x,"
                     "%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,",
                     c->frame_id, (long long)h->t_us, c->rx_us,
                     c->src[0], c->src[1], c->src[2], c->src[3], c->src[4], c->src[5],
                     c->dst[0], c->dst[1], c->dst[2], c->dst[3], c->dst[4], c->dst[5],
                     c->rssi, c->noise_floor, c->channel, c->secondary, c->sig_mode, c->mcs,
                     c->cwb, c->stbc, c->rate, c->rx_seq, c->flags & 1, c->orig_len, c->csi_len);
    n += b64_encode((const uint8_t *)(c + 1), c->csi_len, line + n);
    line[n++] = '\n';
    uart_write_paced(line, n);
    s_tx_bytes += n;
}

/* uart_write_bytes() spins when its TX ring is full (measured: 97 % of a core
 * at saturation), so wait for room with a sleeping delay instead. */
static void uart_write_paced(const void *buf, size_t len)
{
    size_t free_bytes = 0;
    while (uart_get_tx_buffer_free_size(UART_PORT, &free_bytes) == ESP_OK && free_bytes < len) {
        vTaskDelay(1);
    }
    uart_write_bytes(UART_PORT, buf, len);
}

static void transport_task(void *arg);

static void spawn_transport(int core)
{
    if (xTaskCreatePinnedToCore(transport_task, "transport", 6144, NULL,
                                CONFIG_RADAR_TRANSPORT_PRIO, NULL, core) != pdPASS) {
        ESP_LOGE(TAG, "failed to create transport task on core %d", core);
    }
}

void telemetry_set_transport_core(int core)
{
    s_transport_core = core ? 1 : 0;
}

static void transport_task(void *arg)
{
    ESP_LOGI(TAG, "transport task on core %d", xPortGetCoreID());
    for (;;) {
        if (s_transport_core != xPortGetCoreID()) {
            /* Hand over between packets: nothing is held at this point. */
            spawn_transport(s_transport_core);
            vTaskDelete(NULL);
        }
        int a = s_active;
        size_t size = 0;
        RingbufHandle_t ring = s_ring[RING_CTRL];
        uint8_t *item = xRingbufferReceive(ring, &size, 0);
        if (item == NULL) {
            ring = s_ring[a];
            item = xRingbufferReceive(ring, &size, pdMS_TO_TICKS(2));
        }
        if (item == NULL && s_ring[!a]) {
            ring = s_ring[!a];
            item = xRingbufferReceive(ring, &size, 0);
        }
        if (item == NULL) {
            continue;
        }
        radar_hdr_t *h = (radar_hdr_t *)item;
        uint64_t now = esp_timer_get_time();
        uint32_t wait = (uint32_t)(now - h->t_us);
        s_wait_sum += wait;
        if (wait > s_wait_max) {
            s_wait_max = wait;
        }

        bool is_data = h->type == RADAR_PKT_CSI || h->type == RADAR_PKT_BENCH;
        /* uart-bin carries the whole binary stream on UART0 (COM-only setups);
         * uart-text is the v0.1 baseline: CSI text on UART0, control on USB. */
        radar_sink_t sink = (is_data || s_sink == RADAR_SINK_UART_BIN) ? s_sink : usb_sink();
        int link = (sink == RADAR_SINK_UART_BIN || sink == RADAR_SINK_UART_TXT) ? LINK_UART : LINK_USB;

        if (sink == RADAR_SINK_UART_TXT) {
            if (h->type == RADAR_PKT_CSI) {
                write_csi_text(h);
                s_tx_pkts++;
            }
            /* BENCH has no text form; the baseline benchmark uses real CSI only */
        } else {
            h->flags = 0;
            h->seq = s_link_seq[link]++;
            uint32_t crc = esp_rom_crc32_le(0, item, size - RADAR_CRC_LEN);
            memcpy(item + size - RADAR_CRC_LEN, &crc, RADAR_CRC_LEN);
            int64_t t0 = esp_timer_get_time();
            bool sent = true;
            if (link == LINK_UART) {
                uart_write_paced(item, size);
            } else {
                sent = link_usb_write(item, size);
            }
            if (!sent) {
                s_link_drops++;
            } else if (is_data) {
                s_tx_write_us += (uint32_t)(esp_timer_get_time() - t0);
                s_tx_bytes += size;
                s_tx_pkts++;
            }
        }
        vRingbufferReturnItem(ring, item);
    }
}

/* ---------------- benchmark producer (core 0) ---------------- */

static void bench_task(void *arg)
{
    uint32_t bench_seq = 0;
    uint32_t credit_milli = 0;
    for (;;) {
        uint16_t size = s_bench_size;
        uint32_t pps = s_bench_pps;
        if (size == 0) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        /* Packets allowed this 1 ms tick. pps == 0: until the ring is full. */
        uint32_t budget = 256;
        if (pps) {
            credit_milli += pps;
            budget = credit_milli / 1000;
            credit_milli %= 1000;
        }
        for (uint32_t i = 0; i < budget; i++) {
            uint8_t *p = telemetry_reserve(RADAR_PKT_BENCH, size, esp_timer_get_time());
            if (p == NULL) {
                s_bench_drops++;
                bench_seq++;   /* keep numbering so the host sees the gap */
                if (pps == 0) {
                    break;
                }
                continue;
            }
            memcpy(p, &bench_seq, 4);
            for (uint16_t k = 4; k < size; k++) {
                p[k] = (uint8_t)(bench_seq + k);
            }
            telemetry_commit(p);
            bench_seq++;
            s_bench_generated++;
        }
        vTaskDelay(1);
    }
}

void telemetry_bench(uint32_t pps, uint16_t size)
{
    if (size != 0 && size < 4) {
        size = 4;
    }
    s_bench_pps = pps;
    s_bench_size = size;
    ESP_LOGI(TAG, "bench %s: %" PRIu32 " pkt/s (%s), %u B payload", size ? "on" : "off", pps,
             pps ? "paced" : "max", size);
}

/* ---------------- control ---------------- */

esp_err_t telemetry_set_data_sink(radar_sink_t sink)
{
    if (sink == RADAR_SINK_TINYUSB && !link_usb_is_tinyusb()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (sink == RADAR_SINK_USB_JTAG && link_usb_is_tinyusb()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    s_sink = sink;
    ESP_LOGI(TAG, "data sink -> %s", telemetry_sink_name(sink));
    return ESP_OK;
}

radar_sink_t telemetry_data_sink(void)
{
    return s_sink;
}

void telemetry_use_psram_ring(bool psram)
{
    if (psram && s_ring[1] == NULL) {
        ESP_LOGE(TAG, "no PSRAM ring available");
        return;
    }
    s_active = psram ? 1 : 0;
    s_ring_free_min = UINT32_MAX;
    ESP_LOGI(TAG, "producers now use the %s ring (%u KiB)", psram ? "PSRAM" : "internal",
             (unsigned)(s_ring_size[s_active] / 1024));
}

void telemetry_fill_stat(radar_stat_t *st)
{
    st->ring_size = s_ring_size[s_active];
    uint32_t free_min = s_ring_free_min;
    st->ring_free_min = free_min == UINT32_MAX ? xRingbufferGetCurFreeSize(s_ring[s_active]) : free_min;
    s_ring_free_min = UINT32_MAX;
    st->ring_in_psram = s_active;
    st->data_sink = s_sink;
    st->tx_bytes = s_tx_bytes;
    st->tx_pkts = s_tx_pkts;
    st->tx_write_us = s_tx_write_us;
    s_tx_write_us = 0;
    st->ring_wait_us_max = s_wait_max;
    st->ring_wait_us_sum = s_wait_sum;
    s_wait_max = 0;
    s_wait_sum = 0;
    st->ctrl_drops = s_ctrl_drops;
    st->bench_generated = s_bench_generated;
    st->bench_drops = s_bench_drops;
    st->link_drops = s_link_drops;
}

void telemetry_reboot_to_download(void)
{
    ESP_LOGW(TAG, "rebooting into ROM download mode");
    vTaskDelay(pdMS_TO_TICKS(100));
    link_usb_release();
    REG_WRITE(RTC_CNTL_OPTION1_REG, RTC_CNTL_FORCE_DOWNLOAD_BOOT);
    esp_restart();
}

static void handle_bytes(char *line, size_t *pos, const uint8_t *chunk, int n)
{
    for (int i = 0; i < n; i++) {
        char c = (char)chunk[i];
        if (c == '\r' || c == '\n') {
            if (*pos > 0) {
                line[*pos] = '\0';
                s_handler(line);
                *pos = 0;
            }
        } else if (*pos < CMD_MAX_LEN - 1) {
            line[(*pos)++] = c;
        } else {
            ESP_LOGE(TAG, "command too long, discarded");
            *pos = 0;
        }
    }
}

static void cmd_usb_task(void *arg)
{
    char line[CMD_MAX_LEN];
    size_t pos = 0;
    uint8_t chunk[64];
    for (;;) {
        int n = link_usb_read(chunk, sizeof(chunk), portMAX_DELAY);
        handle_bytes(line, &pos, chunk, n);
    }
}

static void cmd_uart_task(void *arg)
{
    char line[CMD_MAX_LEN];
    size_t pos = 0;
    uint8_t chunk[64];
    for (;;) {
        /* uart_read_bytes waits for the full length, so block for one byte and
         * then take whatever else is already buffered. */
        int n = uart_read_bytes(UART_PORT, chunk, 1, portMAX_DELAY);
        size_t avail = 0;
        uart_get_buffered_data_len(UART_PORT, &avail);
        if (n == 1 && avail > 0) {
            n += uart_read_bytes(UART_PORT, chunk + 1, avail < sizeof(chunk) - 1 ? avail : sizeof(chunk) - 1, 0);
        }
        handle_bytes(line, &pos, chunk, n);
    }
}

esp_err_t telemetry_start_cmd_reader(telemetry_cmd_handler_t handler)
{
    s_handler = handler;
    if (xTaskCreatePinnedToCore(cmd_usb_task, "cmd_usb", 4096, NULL, 3, NULL, 1) != pdPASS ||
        xTaskCreatePinnedToCore(cmd_uart_task, "cmd_uart", 4096, NULL, 3, NULL, 1) != pdPASS) {
        ESP_LOGE(TAG, "failed to create command reader tasks");
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t telemetry_init(void)
{
    /* UART0: CH343 debug channel (text logs) or data sink. */
    esp_err_t err = uart_driver_install(UART_PORT, 1024, UART_TX_BUF, 0, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "uart_driver_install failed: %s", esp_err_to_name(err));
        return err;
    }
    uart_wait_tx_idle_polling(UART_PORT);
    uart_set_baudrate(UART_PORT, UART_BAUD);

    err = link_usb_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "USB link init failed: %s", esp_err_to_name(err));
        return err;
    }
    /* Pick the link the PC is actually on: native USB if a host shows up
     * within 1.5 s (SOF-based), otherwise the whole binary stream on UART0. */
    s_sink = RADAR_SINK_UART_BIN;
    for (int i = 0; i < 15; i++) {
        if (link_usb_connected()) {
            s_sink = usb_sink();
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }

    s_ring_size[0] = RING_INT_SIZE;
    s_ring[0] = xRingbufferCreateWithCaps(RING_INT_SIZE, RINGBUF_TYPE_NOSPLIT,
                                          MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (s_ring[0] == NULL) {
        ESP_LOGE(TAG, "failed to allocate %d B internal ring", RING_INT_SIZE);
        return ESP_ERR_NO_MEM;
    }
    s_ring_size[RING_CTRL] = RING_CTRL_SIZE;
    s_ring[RING_CTRL] = xRingbufferCreateWithCaps(RING_CTRL_SIZE, RINGBUF_TYPE_NOSPLIT,
                                                  MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (s_ring[RING_CTRL] == NULL) {
        ESP_LOGE(TAG, "failed to allocate control ring");
        return ESP_ERR_NO_MEM;
    }
    s_ring_size[1] = RING_PSRAM_SIZE;
    s_ring[1] = xRingbufferCreateWithCaps(RING_PSRAM_SIZE, RINGBUF_TYPE_NOSPLIT,
                                          MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (s_ring[1] == NULL) {
        ESP_LOGE(TAG, "failed to allocate %d B PSRAM ring (continuing without it)", RING_PSRAM_SIZE);
    }

    spawn_transport(s_transport_core);
    if (xTaskCreatePinnedToCore(bench_task, "bench", 3072, NULL, 4, NULL, 0) != pdPASS) {
        ESP_LOGE(TAG, "failed to create transport/bench tasks");
        return ESP_ERR_NO_MEM;
    }
    esp_log_set_vprintf(log_hook);
    ESP_LOGI(TAG, "rings: internal %d KiB, PSRAM %d KiB; USB host %s -> data sink %s; UART0 %d baud",
             RING_INT_SIZE / 1024, s_ring[1] ? RING_PSRAM_SIZE / 1024 : 0,
             link_usb_connected() ? "present" : "absent", telemetry_sink_name(s_sink), UART_BAUD);
    return ESP_OK;
}
