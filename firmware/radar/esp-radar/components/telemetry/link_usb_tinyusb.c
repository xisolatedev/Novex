#include "sdkconfig.h"
#if CONFIG_RADAR_USB_TINYUSB
#include "link_usb.h"
#include "esp_log.h"
#include "freertos/stream_buffer.h"
#include "tinyusb.h"
#include "tinyusb_default_config.h"
#include "tinyusb_cdc_acm.h"
#include "hal/usb_serial_jtag_ll.h"
#include "tusb.h"

static const char *TAG = "link_tusb";
static StreamBufferHandle_t s_rx;

static void on_rx(int itf, cdcacm_event_t *event)
{
    static uint8_t buf[CONFIG_TINYUSB_CDC_RX_BUFSIZE]; /* TinyUSB task context, not reentrant */
    size_t n = 0;
    if (tinyusb_cdcacm_read(itf, buf, sizeof(buf), &n) == ESP_OK && n > 0) {
        xStreamBufferSend(s_rx, buf, n, 0);
    }
}

esp_err_t link_usb_init(void)
{
    s_rx = xStreamBufferCreate(1024, 1);
    const tinyusb_config_t cfg = TINYUSB_DEFAULT_CONFIG();
    esp_err_t err = tinyusb_driver_install(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "tinyusb_driver_install: %s", esp_err_to_name(err));
        return err;
    }
    const tinyusb_config_cdcacm_t acm = {
        .cdc_port = TINYUSB_CDC_ACM_0,
        .callback_rx = on_rx,
    };
    err = tinyusb_cdcacm_init(&acm);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "tinyusb_cdcacm_init: %s", esp_err_to_name(err));
    }
    ESP_LOGI(TAG, "TinyUSB CDC-ACM up (ep buf %d, tx fifo %d)", CONFIG_TINYUSB_CDC_EP_BUFSIZE,
             CONFIG_TINYUSB_CDC_TX_BUFSIZE);
    return err;
}

bool link_usb_connected(void)
{
    return tud_mounted();
}

bool link_usb_write(const void *buf, size_t len)
{
    const uint8_t *p = buf;
    while (len > 0) {
        if (!tud_mounted()) {
            return false;
        }
        size_t n = tinyusb_cdcacm_write_queue(TINYUSB_CDC_ACM_0, p, len);
        p += n;
        len -= n;
        if (len > 0) {
            /* FIFO full: push it out and wait for room (host must be reading). */
            tinyusb_cdcacm_write_flush(TINYUSB_CDC_ACM_0, pdMS_TO_TICKS(20));
        }
    }
    tinyusb_cdcacm_write_flush(TINYUSB_CDC_ACM_0, 0);
    return true;
}

int link_usb_read(void *buf, size_t len, TickType_t timeout)
{
    return xStreamBufferReceive(s_rx, buf, len, timeout);
}

bool link_usb_is_tinyusb(void)
{
    return true;
}

void link_usb_release(void)
{
    tinyusb_driver_uninstall();
    vTaskDelay(pdMS_TO_TICKS(200));   /* let the host see the detach */
    /* TinyUSB mapped the internal PHY to USB-OTG via an RTC-domain register that
     * survives a software reset; without this the ROM's USB-Serial/JTAG
     * downloader has no PHY and the host sees error -71. */
    usb_serial_jtag_ll_phy_enable_external(false);
}
#else
#include "link_usb.h"
void link_usb_release(void)
{
}
#endif
