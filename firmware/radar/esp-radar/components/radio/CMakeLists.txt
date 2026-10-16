idf_component_register(SRCS "radio.c"
                       INCLUDE_DIRS "include"
                       REQUIRES esp_wifi
                       PRIV_REQUIRES esp_netif esp_event nvs_flash telemetry)
