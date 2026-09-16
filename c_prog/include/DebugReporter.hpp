#pragma once

#include "DebugStatistics.hpp"

#include <cstdio>

namespace novex
{

// Prints the end-of-run --debug report.
//
// Written to stdout, deliberately, while all normal logging goes to
// stderr. That keeps the report cleanly separated: `novex-vio --debug
// 2>/dev/null` gives you the report alone, and `> /dev/null` gives you
// the log alone.
class DebugReporter
{
public:

    static void print(const DebugStatistics& statistics,
                      FILE* out = stdout);
};

} // namespace novex
