idf_component_register(SRCS "main.c"
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES radio csi telemetry esp_wifi esp_timer spi_flash)
