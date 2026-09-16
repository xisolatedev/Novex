/* Smooth HSV Rainbow Cycle for ESP32-S3 Built-in RGB LED */

#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "led_strip.h"
#include "sdkconfig.h"

static const char *TAG = "rainbow_example";

#define BLINK_GPIO CONFIG_BLINK_GPIO

#ifdef CONFIG_BLINK_LED_STRIP

static led_strip_handle_t led_strip;

static void configure_led(void)
{
    ESP_LOGI(TAG, "Configuring addressable RGB LED...");
    
    led_strip_config_t strip_config = {
        .strip_gpio_num = BLINK_GPIO,
        .max_leds = 1,
    };
#if CONFIG_BLINK_LED_STRIP_BACKEND_RMT
    led_strip_rmt_config_t rmt_config = {
        .resolution_hz = 10 * 1000 * 1000, // 10MHz
        .flags.with_dma = false,
    };
    ESP_ERROR_CHECK(led_strip_new_rmt_device(&strip_config, &rmt_config, &led_strip));
#elif CONFIG_BLINK_LED_STRIP_BACKEND_SPI
    led_strip_spi_config_t spi_config = {
        .spi_bus = SPI2_HOST,
        .flags.with_dma = true,
    };
    ESP_ERROR_CHECK(led_strip_new_spi_device(&strip_config, &spi_config, &led_strip));
#else
#error "unsupported LED strip backend"
#endif

    led_strip_clear(led_strip);
}

// Convert HSV color space (h: 0-360, s: 0-255, v: 0-255) to RGB values
static void hsv_to_rgb(uint16_t h, uint8_t s, uint8_t v, uint32_t *r, uint32_t *g, uint32_t *b)
{
    uint8_t region, remainder, p, q, t;

    if (s == 0) {
        *r = *g = *b = v;
        return;
    }

    region = h / 60;
    remainder = (h % 60) * 255 / 60;

    p = (v * (255 - s)) >> 8;
    q = (v * (255 - ((s * remainder) >> 8))) >> 8;
    t = (v * (255 - ((s * (255 - remainder)) >> 8))) >> 8;

    switch (region) {
        case 0:  *r = v; *g = t; *b = p; break;
        case 1:  *r = q; *g = v; *b = p; break;
        case 2:  *r = p; *g = v; *b = t; break;
        case 3:  *r = p; *g = q; *b = v; break;
        case 4:  *r = t; *g = p; *b = v; break;
        default: *r = v; *g = p; *b = q; break;
    }
}

void app_main(void)
{
    configure_led();

    uint16_t hue = 0;
    uint32_t red = 0, green = 0, blue = 0;

    while (1) {
        // Convert current hue to RGB (Max brightness set to 20 to avoid blinding light)
        hsv_to_rgb(hue, 255, 20, &red, &green, &blue);

        // Apply color to LED 0
        led_strip_set_pixel(led_strip, 0, red, green, blue);
        led_strip_refresh(led_strip);

        // Increment hue and loop back at 360 degrees
        hue = (hue + 1) % 360;

        // 10ms delay gives a fluid ~3.6 second rainbow revolution
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

#else
#error "This smooth color code requires an addressable RGB LED strip configuration."
#endif