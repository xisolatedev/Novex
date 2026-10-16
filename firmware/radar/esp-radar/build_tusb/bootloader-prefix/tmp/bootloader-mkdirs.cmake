# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file LICENSE.rst or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION ${CMAKE_VERSION}) # this file comes with cmake

# If CMAKE_DISABLE_SOURCE_CHANGES is set to true and the source directory is an
# existing directory in our source tree, calling file(MAKE_DIRECTORY) on it
# would cause a fatal error, even though it would be a no-op.
if(NOT EXISTS "/home/isodev/.espressif/v6.1/esp-idf/components/bootloader/subproject")
  file(MAKE_DIRECTORY "/home/isodev/.espressif/v6.1/esp-idf/components/bootloader/subproject")
endif()
file(MAKE_DIRECTORY
  "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader"
  "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader-prefix"
  "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader-prefix/tmp"
  "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader-prefix/src/bootloader-stamp"
  "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader-prefix/src"
  "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader-prefix/src/bootloader-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader-prefix/src/bootloader-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/media/isodev/ca6ce0f1-5feb-46a1-ae3c-00afd2b5117d/Novex/radar/esp-radar/build_tusb/bootloader-prefix/src/bootloader-stamp${cfgdir}") # cfgdir has leading slash
endif()
