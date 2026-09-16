idf_component_register(SRCS "main.cc" "model.cc"
                       INCLUDE_DIRS "."
                       REQUIRES espressif__esp-tflite-micro esp_psram)
