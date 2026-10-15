#pragma once
/* Native USB link: USB-Serial/JTAG peripheral or TinyUSB CDC (Kconfig choice). */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"

esp_err_t link_usb_init(void);
/* Queues buf for the host. Returns false (nothing more sent) if no USB host is
 * attached or the host stops reading; the caller counts the drop. */
bool link_usb_write(const void *buf, size_t len);
/* True while a USB host is attached (USB SOFs seen / device mounted). */
bool link_usb_connected(void);
int link_usb_read(void *buf, size_t len, TickType_t timeout);
bool link_usb_is_tinyusb(void);
/* Called before rebooting to the ROM downloader. */
void link_usb_release(void);
