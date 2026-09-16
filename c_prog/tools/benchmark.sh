#!/usr/bin/env bash
#
# Measures the pipeline as it actually runs, on whatever machine it is
# run on. Nothing here is estimated: every number comes from the
# daemon's own timers, which are driven by real camera timestamps.
#
#   ./tools/benchmark.sh                 default config
#   ./tools/benchmark.sh --features 300  override any novex-vio flag
#
# Reports per-stage milliseconds, measured capture and processing
# frame rates, sensor-to-state latency, dropped frames, peak RSS and
# CPU time.

set -u

BUILD="${BUILD:-build}"
FRAMES="${FRAMES:-600}"
SOCKET="/tmp/novex-bench.sock"

LOG=$(mktemp)
TIMING=$(mktemp)

cleanup()
{
    [ -n "${PID:-}" ] && kill -9 "$PID" 2>/dev/null
    rm -f "$LOG" "$TIMING" "$SOCKET"
}

trap cleanup EXIT

echo "Novex VIO benchmark"
echo "==================="
echo "host    : $(uname -m) $(uname -r)"

if [ -f /proc/cpuinfo ]; then
    MODEL=$(grep -m1 -E 'model name|Model' /proc/cpuinfo | cut -d: -f2- |
            sed 's/^ *//')
    echo "cpu     : ${MODEL:-unknown} x $(nproc)"
fi

if [ -f /proc/device-tree/model ]; then
    echo "board   : $(tr -d '\0' < /proc/device-tree/model)"
fi

echo "frames  : $FRAMES"
echo "extra   : ${*:-none}"
echo

# /usr/bin/time gives peak RSS and CPU time. Falling back cleanly
# because the shell builtin `time` does not report either.
TIME_BIN=""
[ -x /usr/bin/time ] && TIME_BIN=/usr/bin/time

if [ -n "$TIME_BIN" ]; then
    env -u DISPLAY -u WAYLAND_DISPLAY \
        "$TIME_BIN" -v -o "$TIMING" \
        "$BUILD/novex-vio" --mode daemon --socket "$SOCKET" \
        --max-frames "$FRAMES" "$@" > "$LOG" 2>&1 &
else
    env -u DISPLAY -u WAYLAND_DISPLAY \
        "$BUILD/novex-vio" --mode daemon --socket "$SOCKET" \
        --max-frames "$FRAMES" "$@" > "$LOG" 2>&1 &
fi

PID=$!

for _ in $(seq 1 60); do
    [ -S "$SOCKET" ] && break
    sleep 0.25
done

if [ ! -S "$SOCKET" ]; then
    echo "the daemon did not start:"
    cat "$LOG"
    exit 1
fi

# Let the rolling averages fill before sampling.
sleep 6

echo "--- steady-state timings (from the daemon's own counters) ---"
"$BUILD/novex-state" --socket "$SOCKET" --stats |
    tr ',' '\n' | tr -d '{}"' | sed 's/^/  /'

echo
echo "--- state ---"
"$BUILD/novex-state" --socket "$SOCKET" |
    tr ',' '\n' | tr -d '{}"' | sed 's/^/  /'

wait "$PID" 2>/dev/null

echo
echo "--- run summary ---"
grep -E "stopped after" "$LOG" | sed 's/^/  /'
grep -E "perf:" "$LOG" | tail -1 | sed 's/^/  /'

if [ -s "$TIMING" ]; then
    echo
    echo "--- resources ---"
    grep -E "Maximum resident set size|User time|System time|Percent of CPU" \
        "$TIMING" | sed 's/^\s*/  /'
fi

echo
echo "Read it like this:"
echo "  decode_ms + total_ms is the CPU cost of one frame."
echo "  capture_ms is mostly the wait for the sensor and is NOT CPU."
echo "  If decode_ms + total_ms approaches 33 ms, the Pi is at its"
echo "  limit at 30 fps; reduce features.max first, then resolution."
