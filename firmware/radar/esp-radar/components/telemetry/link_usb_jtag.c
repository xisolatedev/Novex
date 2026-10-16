#include "sdkconfig.h"
#if !CONFIG_RADAR_USB_TINYUSB
#include "link_usb.h"
#include "esp_log.h"
#include "driver/usb_serial_jtag.h"

static const char *TAG = "link_usj";

esp_err_t link_usb_init(void)
{
    usb_serial_jtag_driver_config_t cfg = {
        .tx_buffer_size = CONFIG_RADAR_USB_TX_BUF_KB * 1024,
        .rx_buffer_size = 1024,
    };
    esp_err_t err = usb_serial_jtag_driver_install(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "usb_serial_jtag_driver_install: %s", esp_err_to_name(err));
    }
    return err;
}

bool link_usb_write(const void *buf, size_t len)
{
    const uint8_t *p = buf;
    while (len > 0) {
        int n = usb_serial_jtag_write_bytes(p, len, pdMS_TO_TICKS(50));
        if (n <= 0) {
            /* Only a stalled write asks whether the host is gone: the SOF-based
             * check reported false "disconnects" under saturation (20 packets in
             * a 1 MiB PSRAM-ring run). Slow host = keep waiting (back-pressure). */
            if (!usb_serial_jtag_is_connected()) {
                return false;
            }
            continue;
        }
        p += n;
        len -= n;
    }
    return true;
}

bool link_usb_connected(void)
{
    return usb_serial_jtag_is_connected();
}

int link_usb_read(void *buf, size_t len, TickType_t timeout)
{
    return usb_serial_jtag_read_bytes(buf, len, timeout);
}

bool link_usb_is_tinyusb(void)
{
    return false;
}
#endif
