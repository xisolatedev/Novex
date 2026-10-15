# Board-specific workaround: this ESP32-S3 module's flash reports JEDEC ID
# 0x207018 (XMC XM25QH128A). IDF 6.1's strict XMC check only accepts
# 0x2040xx/0x2041xx/0x2050xx, so the stock bootloader reset-loops with
# "XMC flash startup fail". Instead of patching IDF, wrap the check.
idf_component_register(SRCS "xmc_bypass.c"
                       PRIV_REQUIRES bootloader_support log)
target_link_libraries(${COMPONENT_LIB} INTERFACE
    "-Wl,--wrap=bootloader_flash_xmc_startup"
    "-u __wrap_bootloader_flash_xmc_startup")
