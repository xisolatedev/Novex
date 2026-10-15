# radar — ESP32 Wi-Fi CSI research platform

```
radar/
├── esp-radar/                 ESP-IDF 6.1 firmware (ESP32-S3 CSI receiver), v0.2
│   ├── main/                  app_main, host commands, 1 Hz STAT, per-core CPU, `top`
│   ├── components/
│   │   ├── radio/             Wi-Fi bring-up, AP scan, channel, promiscuous filter
│   │   ├── csi/               CSI callback -> zero-copy record in the telemetry ring
│   │   └── telemetry/         rings, transport task, binary framing, USB/UART links, bench
│   │       └── include/radar_proto.h   wire format (mirrored in viewer/radar_bin.py)
│   ├── bootloader_components/xmc_bypass/   board flash-chip workaround (see below)
│   ├── sdkconfig.defaults           default build: native USB via USB-Serial/JTAG
│   └── sdkconfig.tusb.defaults      optional build: native USB via TinyUSB CDC
├── esp-radar-tx/              ESP32-C6 controlled transmitter (ESP-NOW broadcast, HT20 MCS0)
├── viewer/                    Linux tools (Python)
│   ├── radar_bin.py           binary decoder, CRC/resync, clock sync, .radar captures
│   ├── radar_session.py       live session + per-second metrics (shared by CLI and GUI)
│   ├── radar_cli.py           monitor / bench / sweep / cmd
│   ├── radar_viewer.py        live GUI: CSI plots + benchmark panel
│   ├── csiproto.py            CsiFrame + loss trackers (+ v0.1 text parser)
│   └── test_*.py              unit tests
└── captures/                  recordings (.radar), created by the viewer / CLI
```

Not created yet: `dsp/` (Phase 3 signal processing), `ai/` (Phase 5; reuses the esp-training TFLM +
2 MB PSRAM arena setup), and `web/` (Phase 6).

## Commands, in order

```bash
. ~/.espressif/tools/activate_idf_v6.1.sh            # every new terminal

cd radar/esp-radar
idf.py build
idf.py -p /dev/ttyACM0 flash                         # works on the COM port and on the USB (JTAG) port

cd ../viewer
.venv/bin/python radar_viewer.py                     # live GUI (same command on COM or USB)
.venv/bin/python radar_cli.py monitor --seconds 20   # headless, one metrics line per second
.venv/bin/python radar_cli.py sweep --seconds 6      # transport benchmark matrix
.venv/bin/python radar_cli.py bench --pps 1000 --size 480 --seconds 10
.venv/bin/python radar_cli.py cmd "ch 1"             # any device command
.venv/bin/python radar_cli.py monitor --record ../captures/run1.radar
.venv/bin/python -m unittest test_radar_bin test_csiproto
```

Only one program can own `/dev/ttyACM0` at a time. Opening the port reboots the S3 through the
auto-reset lines, and it resumes in about 3.5 s.

The firmware picks its link at boot. If a USB host is detected on the native USB (JTAG) port
within 1.5 s, it streams there. Otherwise the whole binary stream goes to UART0 (COM port, 2 Mbaud).
The viewer uses the same command either way.

Optional TinyUSB build (faster, but flashing it needs BOOT+RST; see findings):
```bash
idf.py -B build_tusb -D SDKCONFIG=sdkconfig.tusb -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.tusb.defaults" build
```

## Controlled source: ESP32-C6 → S3 (no router)

`esp-radar-tx` broadcasts fixed-size ESP-NOW frames: 100 Hz, channel 11, and a 64 B payload
(RDTX magic, tx_seq, t_us). Kconfig `TX_RATE_HZ`, `TX_CHANNEL` and `TX_PAYLOAD_LEN` change these.
Frames are forced to **HT20 MCS0 (OFDM)** because ESP-NOW's default 1 Mbps DSSS rate produces
no CSI. The C6 board also has two ports ("esp32c6" native USB-JTAG and "ch343"). Flash it on the
"esp32c6" port, then run it from any USB power source; it starts transmitting on its own at boot.

```bash
cd esp-radar-tx && idf.py build && idf.py -p /dev/ttyACM0 flash          # C6 on the PC
cd ../viewer && .venv/bin/python radar_cli.py c6 --seconds 30           # S3 on the PC, C6 powered
```

First run (2026-09-26, boards about 1–3 m apart, S3 on native USB):

| metric | result |
|---|---|
| received | 2998 frames in 30 s (≈99/s of 100/s configured) |
| over-the-air loss (802.11 seq) | 30 frames, 0.99 %. Each loss is a 20.00 ms gap = one skipped slot |
| device / USB drops | 0 |
| CSI | HT (sig_mode 1), 256 B = 64 L-LTF + 64 HT-LTF subcarriers, every frame |
| inter-arrival | 10.0–10.3 ms mean, 0.3–1.8 ms std |
| RSSI | −49 dBm, std 0.0–0.7 dB |
| latency acq→PC | 0.1–0.7 ms |

## Architecture

```
core 0                                   core 1
Wi-Fi task (prio 23)                     transport task (prio 10)
  CSI callback ~10-20 µs                   drains control ring first, then data ring
  reserve -> fill -> commit  ──ring──►     assigns link seq, CRC32, writes to USB or UART
  never blocks; full ring = counted drop   never blocks on a missing USB host (counted)
bench task (prio 4, BENCH filler only)   cmd readers (USB + UART)
                                         [future: DSP task -> own ring -> TFLM task]
```

* **Data ring:** 64 KiB internal RAM (default), or 1 MiB PSRAM (`ring psram`). No-split FreeRTOS
  ring buffer. Producers write each record in place (zero-copy), and the CRC is computed on core 1.
* **Control ring:** a separate 16 KiB ring for STAT/LOG/replies, so statistics keep flowing while
  data saturates the link.
* **Every loss is counted:** `csi_ring_drops` (CSI `frame_id` gaps), `bench_drops`, `ctrl_drops`
  and `link_drops` (no host) on the device. The PC counts link `seq` gaps, CRC failures and
  skipped bytes.
* **Why these primitives:** the no-split ring gives variable-size items and zero-copy
  acquire/commit with multiple producers. A stream buffer allows only one writer. The v0.1
  xQueue copied fixed 688-byte slots.

## Wire format (radar_proto.h)

`[hdr 20 B][payload][crc32 4 B]`, little-endian. The header holds sync `A5 5A`, version 1, type,
payload_len, flags, link seq (u32), and t_us (u64, esp_timer at acquisition). The CRC is
zlib/IEEE CRC-32 over header + payload.

| type | payload |
|---|---|
| 1 CSI | 36 B metadata (frame_id, rx_us, src/dst MAC, rssi, noise floor, channel, secondary, sig_mode, mcs, cwb, stbc, rate, flags, rx_seq, orig_len, csi_len) + int8 (imag, real) pairs |
| 2 STAT | 104 B counters: CSI, ring, transport, CPU per core, heap/PSRAM, drops |
| 3 LOG / 4 AP / 5 HELLO / 6 REPLY | text |
| 7 BENCH | u32 seq + byte pattern. Transport filler only, never CSI |
| 8 PONG | ping token + esp_timer, used for clock sync / latency |

Commands: `ch N`, `mac aa:..|any`, `filter mgmt|all`, `csi on|off`, `scan`, `info`, `ping T`,
`sink usb|uart|uart-text`, `ring int|psram`, `tcore 0|1`, `bench PPS BYTES | bench off`, `top`,
`bootloader`.

## Measured results (2026-09-26, this board)

| Link | Max throughput | Zero-drop paced | CPU at max | Latency (real CSI) |
|---|---|---|---|---|
| UART0 / CH343, 2 Mbaud, v0.1 text | ~200 KB/s wire, 444 B/frame | — | — | — |
| UART0 / CH343, 2 Mbaud, binary | 199.6 KB/s | 176 KB/s | 3.5 % (paced writes; 97–99 % before the fix) | 1.8 ms avg, 3.6 ms p95 |
| Native USB, USB-Serial/JTAG (default) | 768 KB/s | 705 KB/s | ~16–18 % core 1 | 0.45–0.6 ms avg, ~1 ms p95 |
| Native USB, TinyUSB CDC (optional) | 1,141 KB/s | 706 KB/s | ~9–15 % core 1 | not measured |

All of these runs had 0 CRC errors and 0 corrupted BENCH payloads. Device-counted drops matched
PC-seen sequence gaps.

Real CSI observed so far (ambient traffic, no C6 yet): up to 517 frames/s. Frames average 188–316 B
in binary versus 444 B in the v0.1 text format (−30 % or more). At 517 frames/s that is about
163 KB/s: over budget for UART text, 82 % of UART binary, 21 % of USB-Serial/JTAG. The CSI
callback takes 6–21 µs on average, 78 µs at most.

## Hardware findings

* **USB is Full Speed only (12 Mbit/s).** The S3 has no high-speed PHY (`SOC_USB_UTMI` is
  absent; the host reports 12 Mbps). Bulk transfers top out near 1.2 MB/s.
* The board has two USB-C ports. **COM** is a CH343 bridge (1a86:55d3) on UART0.
  **USB** is the S3's native USB on GPIO19/20, running USB-Serial/JTAG (303a:1001) by
  default. The S3 has one USB PHY: USB-Serial/JTAG and TinyUSB (USB-OTG) cannot run at the
  same time.
* **TinyUSB is 1.49× faster, but flashing becomes manual.** Once TinyUSB runs, USB-Serial/JTAG
  is gone, so auto-reset flashing stops working. The `bootloader` command hands the PHY back
  and forces ROM download. On the first attempt the host saw `error -71`. A PHY hand-back fix
  is built but unverified, and recovery needed BOOT+RST plus a power cycle. That is why
  USB-Serial/JTAG is the default.
* **The flash chip needs a bootloader workaround.** It reports JEDEC ID 0x207018 (XMC), which
  IDF 6.1's strict XMC check rejects, so the stock bootloader reset-loops.
  `bootloader_components/xmc_bypass` wraps `bootloader_flash_xmc_startup` with `-Wl,--wrap`
  and continues only for that exact ID. IDF itself is unmodified.
* The PC's Wi-Fi is on 5 GHz channel 140, so it can't generate 2.4 GHz test traffic. Stress
  tests use labeled BENCH filler. Controlled real CSI at a fixed rate needs the C6.
