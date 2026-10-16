#pragma once
/*
 * esp-radar binary wire format, version 1. Mirrored in viewer/radar_bin.py.
 *
 *   [radar_hdr_t 20 B][payload payload_len B][crc32 4 B]
 *
 * All fields little-endian and packed. crc32 is standard CRC-32 (zlib / IEEE
 * 802.3) over header + payload. The host resynchronises on the sync bytes and
 * rejects any packet whose CRC fails.
 */
#include <stdint.h>

#define RADAR_SYNC0        0xA5
#define RADAR_SYNC1        0x5A
#define RADAR_PROTO_VER    1
#define RADAR_CRC_LEN      4
#define RADAR_CSI_MAX_LEN  640   /* largest documented CSI buffer is 612 B (HT40 + STBC) */

typedef enum {
    RADAR_PKT_CSI   = 1,   /* radar_csi_t + int8 CSI buffer */
    RADAR_PKT_STAT  = 2,   /* radar_stat_t, 1 Hz */
    RADAR_PKT_LOG   = 3,   /* ESP_LOG text (UTF-8, no terminator) */
    RADAR_PKT_AP    = 4,   /* text "bssid,ch,rssi,auth,ssid" */
    RADAR_PKT_HELLO = 5,   /* text "key=value,..." */
    RADAR_PKT_REPLY = 6,   /* text "ACK,..." or "ERR,..." */
    RADAR_PKT_BENCH = 7,   /* transport benchmark filler: u32 bench_seq + pattern. NOT CSI. */
    RADAR_PKT_PONG  = 8,   /* radar_pong_t, clock-offset probe */
} radar_pkt_type_t;

typedef struct __attribute__((packed)) {
    uint8_t  sync[2];      /* A5 5A */
    uint8_t  version;
    uint8_t  type;         /* radar_pkt_type_t */
    uint16_t payload_len;
    uint16_t flags;        /* reserved, 0 */
    uint32_t seq;          /* transport sequence, assigned when written to the link */
    uint64_t t_us;         /* esp_timer time the record was produced (CSI: callback entry) */
} radar_hdr_t;

typedef struct __attribute__((packed)) {
    uint32_t frame_id;     /* per accepted CSI frame; gaps = frames dropped on the device */
    uint32_t rx_us;        /* radio RX timestamp (rx_ctrl.timestamp) */
    uint8_t  src[6];
    uint8_t  dst[6];
    int8_t   rssi;
    int8_t   noise_floor;
    uint8_t  channel;
    uint8_t  secondary;
    uint8_t  sig_mode;
    uint8_t  mcs;
    uint8_t  cwb;
    uint8_t  stbc;
    uint8_t  rate;
    uint8_t  flags;        /* bit0 first_word_invalid, bit1 truncated */
    uint16_t rx_seq;
    uint16_t orig_len;
    uint16_t csi_len;      /* bytes that follow: int8 pairs (imag, real) */
} radar_csi_t;

typedef struct __attribute__((packed)) {
    uint32_t uptime_ms;
    /* acquisition (core 0, Wi-Fi task) */
    uint32_t csi_callbacks;
    uint32_t csi_filtered;
    uint32_t csi_accepted;
    uint32_t csi_ring_drops;     /* accepted but ring full -> dropped, counted */
    uint32_t csi_truncated;
    uint32_t cb_us_max;          /* CSI callback duration, max since last STAT */
    uint32_t cb_us_sum;          /* sum since last STAT (avg = sum / accepted delta) */
    /* ring buffer */
    uint32_t ring_size;
    uint32_t ring_free_min;      /* low-water mark since last STAT */
    uint8_t  ring_in_psram;
    uint8_t  data_sink;          /* radar_sink_t */
    uint8_t  channel;
    uint8_t  promisc_data;
    /* transport (core 1) */
    uint32_t tx_bytes;           /* total bytes handed to the data sink */
    uint32_t tx_pkts;
    uint32_t tx_write_us;        /* time spent inside sink writes since last STAT */
    uint32_t ring_wait_us_max;   /* produce -> write latency on the device, max since last STAT */
    uint32_t ring_wait_us_sum;   /* sum since last STAT (avg = sum / tx_pkts delta) */
    uint32_t ctrl_drops;         /* STAT/LOG/REPLY packets lost to a full ring */
    uint32_t bench_generated;
    uint32_t bench_drops;
    /* cpu, permille busy since last STAT */
    uint16_t cpu0_permille;
    uint16_t cpu1_permille;
    /* memory */
    uint32_t heap_int_free;
    uint32_t heap_int_min;
    uint32_t heap_int_largest;
    uint32_t psram_free;
    uint32_t psram_total;
    uint32_t link_drops;         /* packets discarded because their link had no host */
} radar_stat_t;

typedef struct __attribute__((packed)) {
    uint64_t pc_token;           /* echoed from "ping <token>" */
    uint64_t esp_us;             /* esp_timer when the ping was handled */
} radar_pong_t;

typedef enum {
    RADAR_SINK_USB_JTAG = 0,     /* native USB, USB-Serial/JTAG peripheral (binary) */
    RADAR_SINK_UART_BIN = 1,     /* UART0 @ 2 Mbaud via CH343 (binary) */
    RADAR_SINK_UART_TXT = 2,     /* UART0 @ 2 Mbaud, v0.1 text lines (baseline) */
    RADAR_SINK_TINYUSB  = 3,     /* native USB, TinyUSB CDC-ACM (binary) */
} radar_sink_t;

/* Layout is part of the wire format (viewer/radar_bin.py asserts the same). */
_Static_assert(sizeof(radar_hdr_t) == 20, "radar_hdr_t size");
_Static_assert(sizeof(radar_csi_t) == 36, "radar_csi_t size");
_Static_assert(sizeof(radar_stat_t) == 104, "radar_stat_t size");
_Static_assert(sizeof(radar_pong_t) == 16, "radar_pong_t size");
