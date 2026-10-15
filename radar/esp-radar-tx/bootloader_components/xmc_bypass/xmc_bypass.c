#include <inttypes.h>
#include "esp_err.h"
#include "esp_log.h"
#include "esp_attr.h"
#include "esp_rom_spiflash.h"

/* Flash chip on this board; see CMakeLists.txt */
#define KNOWN_XMC_ID 0x207018

static const char *TAG = "xmc_bypass";

esp_err_t __real_bootloader_flash_xmc_startup(void);

esp_err_t IRAM_ATTR __wrap_bootloader_flash_xmc_startup(void)
{
    esp_err_t ret = __real_bootloader_flash_xmc_startup();
    if (ret != ESP_OK && g_rom_flashchip.device_id == KNOWN_XMC_ID) {
        ESP_EARLY_LOGW(TAG, "XMC startup check failed for known ID 0x%" PRIx32 ", continuing",
                       g_rom_flashchip.device_id);
        return ESP_OK;
    }
    return ret;
}
