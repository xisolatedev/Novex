#!/usr/bin/env bash
#
# End-to-end lifecycle checks that cannot be made from inside the
# process: daemon startup, IPC from a separate process, and clean
# shutdown on a real signal.
#
# Run from the project root:  ./tests/test_lifecycle.sh

set -u

BUILD="${BUILD:-build}"
SOCKET="/tmp/novex-vio-lifecycle.sock"

pass=0
fail=0

ok()   { echo "    PASS  $1"; pass=$((pass+1)); }
bad()  { echo "    FAIL  $1"; fail=$((fail+1)); }

cleanup()
{
    [ -n "${DAEMON_PID:-}" ] && kill -9 "$DAEMON_PID" 2>/dev/null
    rm -f "$SOCKET"
}

trap cleanup EXIT

echo "Novex VIO lifecycle checks"
echo "=========================="

# ------------------------------------------------------------------
echo
echo "--- 9. daemon mode starts with no display"
# ------------------------------------------------------------------

# env -u DISPLAY proves the daemon needs no X11 session at all, which
# is the condition it will actually run under on the Pi over SSH.
env -u DISPLAY -u WAYLAND_DISPLAY \
    "$BUILD/novex-vio" --mode daemon --no-imu \
    --socket "$SOCKET" > /tmp/novex-daemon.log 2>&1 &

DAEMON_PID=$!

for _ in $(seq 1 50); do
    [ -S "$SOCKET" ] && break
    sleep 0.2
done

if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
    bad "daemon exited during start-up"
    echo "--- daemon log ---"
    cat /tmp/novex-daemon.log
    exit 1
fi

if [ -S "$SOCKET" ]; then
    ok "daemon running headless, socket created at $SOCKET"
else
    bad "no socket appeared"
fi

if grep -qi "imshow\|cannot open display\|gtk" /tmp/novex-daemon.log; then
    bad "daemon touched the display"
else
    ok "no display access attempted"
fi

# ------------------------------------------------------------------
echo
echo "--- 14. a separate process can request state"
# ------------------------------------------------------------------

sleep 2

STATE=$("$BUILD/novex-state" --socket "$SOCKET")

if echo "$STATE" | grep -q '"position"'; then
    ok "GET_STATE returned a state"
    echo "    $STATE"
else
    bad "GET_STATE returned: $STATE"
fi

STATS=$("$BUILD/novex-state" --socket "$SOCKET" --stats)

if echo "$STATS" | grep -q '"processing_fps"'; then
    ok "GET_STATS returned timings"
    echo "    $STATS"
else
    bad "GET_STATS returned: $STATS"
fi

# ------------------------------------------------------------------
echo
echo "--- 15. VIO keeps running while clients come and go"
# ------------------------------------------------------------------

FRAME_BEFORE=$("$BUILD/novex-state" --socket "$SOCKET" |
               sed 's/.*"frame_id":\([0-9]*\).*/\1/')

# Note: wait must name the client PIDs. A bare `wait` would also
# wait for the daemon, which never exits on its own.
CLIENT_PIDS=""

for _ in $(seq 1 20); do
    "$BUILD/novex-state" --socket "$SOCKET" > /dev/null 2>&1 &
    CLIENT_PIDS="$CLIENT_PIDS $!"
done

for p in $CLIENT_PIDS; do
    wait "$p" 2>/dev/null
done

sleep 2

FRAME_AFTER=$("$BUILD/novex-state" --socket "$SOCKET" |
              sed 's/.*"frame_id":\([0-9]*\).*/\1/')

ADVANCED=$((FRAME_AFTER - FRAME_BEFORE))

# 20 clients connecting and disconnecting, then 2 s of running. At
# 30 fps that should be around 60 frames; anything well above zero
# proves the loop was never parked.
if [ "$ADVANCED" -gt 30 ]; then
    ok "processed $ADVANCED frames across 20 client connections"
else
    bad "only $ADVANCED frames advanced; the loop may have stalled"
fi

# ------------------------------------------------------------------
echo
echo "--- 16. SIGTERM shuts down cleanly"
# ------------------------------------------------------------------

kill -TERM "$DAEMON_PID"

EXITED=0

for _ in $(seq 1 50); do
    if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
        EXITED=1
        break
    fi
    sleep 0.2
done

wait "$DAEMON_PID" 2>/dev/null
STATUS=$?

if [ "$EXITED" -eq 1 ]; then
    ok "process exited on SIGTERM (status $STATUS)"
else
    bad "process ignored SIGTERM"
fi

if grep -q "signal received; shutting down" /tmp/novex-daemon.log; then
    ok "shutdown path ran"
else
    bad "no clean-shutdown message in the log"
fi

if grep -q "novex-vio stopped after" /tmp/novex-daemon.log; then
    ok "teardown completed and reported its counters"
    grep "novex-vio stopped after" /tmp/novex-daemon.log | sed 's/^/    /'
else
    bad "teardown did not complete"
fi

if [ -S "$SOCKET" ]; then
    bad "the socket was left behind"
else
    ok "socket removed on exit"
fi

# ------------------------------------------------------------------
echo
echo "--- SIGINT also shuts down cleanly"
# ------------------------------------------------------------------

env -u DISPLAY "$BUILD/novex-vio" --mode daemon --no-imu \
    --socket "$SOCKET" > /tmp/novex-daemon2.log 2>&1 &

DAEMON_PID=$!

sleep 3
kill -INT "$DAEMON_PID"

EXITED=0
for _ in $(seq 1 50); do
    if ! kill -0 "$DAEMON_PID" 2>/dev/null; then EXITED=1; break; fi
    sleep 0.2
done

if [ "$EXITED" -eq 1 ]; then
    ok "process exited on SIGINT"
else
    bad "process ignored SIGINT"
fi

DAEMON_PID=""

echo
echo "=========================="
echo "passed $pass, failed $fail"

[ "$fail" -eq 0 ]
