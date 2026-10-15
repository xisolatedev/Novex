set(reqs esp_driver_uart esp_ringbuf esp_timer esp_rom)
if(CONFIG_RADAR_USB_TINYUSB)
    list(APPEND reqs espressif__esp_tinyusb esp_hal_usb)
else()
    list(APPEND reqs esp_driver_usb_serial_jtag)
endif()
idf_component_register(SRCS "telemetry.c" "link_usb_jtag.c" "link_usb_tinyusb.c"
                       INCLUDE_DIRS "include"
                       PRIV_REQUIRES ${reqs})
