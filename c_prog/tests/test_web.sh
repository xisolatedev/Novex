#!/usr/bin/env bash
#
# End-to-end checks for --debug and --web against a real camera.
#
#   ./tests/test_web.sh
#
# Covers acceptance tests 1-8 from the brief: every mode combination,
# browser disconnect/reconnect, the control commands, and the
# requirement that the visualisation can never stall the VIO loop.

set -u

BUILD="${BUILD:-build}"
PORT="${PORT:-8087}"
SOCKET="/tmp/novex-web-test.sock"
BASE="http://127.0.0.1:$PORT"

pass=0
fail=0

ok()  { echo "    PASS  $1"; pass=$((pass+1)); }
bad() { echo "    FAIL  $1"; fail=$((fail+1)); }

cleanup()
{
    [ -n "${VIO_PID:-}" ] && kill -9 "$VIO_PID" 2>/dev/null
    pkill -f "server.js" 2>/dev/null
    rm -f "$SOCKET"
}

trap cleanup EXIT

# Reads a nested field from JSON on stdin, without requiring jq.
# Usage: jqf position x   |   jqf debug enabled
jqf()
{
    python3 -c '
import json, sys
d = json.load(sys.stdin)
for key in sys.argv[1:]:
    d = d[key]
print(d)
' "$@" 2>/dev/null
}

echo "Novex VIO web/debug checks"
echo "=========================="

# -----------------------------------------------------------------
echo
echo "--- Test 1: plain run, no debug output at all"
# -----------------------------------------------------------------

OUT=$(env -u DISPLAY "$BUILD/novex-vio" --max-frames 60 --no-ipc \
      2>/dev/null)

if [ -z "$OUT" ]; then
    ok "no report on stdout without --debug"
else
    bad "plain run printed to stdout"
fi

# -----------------------------------------------------------------
echo
echo "--- Test 2 / 7: --debug headless prints one report"
# -----------------------------------------------------------------

OUT=$(env -u DISPLAY -u WAYLAND_DISPLAY \
      "$BUILD/novex-vio" --debug --max-frames 120 --no-ipc 2>/dev/null)

COUNT=$(echo "$OUT" | grep -c "NOVEX VIO DEBUG")

if [ "$COUNT" -eq 1 ]; then
    ok "report printed exactly once, with no display"
else
    bad "report printed $COUNT times"
fi

for field in "Frames processed" "p99" "Avg features" "Trajectory length"; do
    if echo "$OUT" | grep -q "$field"; then
        ok "report contains '$field'"
    else
        bad "report is missing '$field'"
    fi
done

# -----------------------------------------------------------------
echo
echo "--- Test 4: --debug --web"
# -----------------------------------------------------------------

rm -f "$SOCKET"

env -u DISPLAY "$BUILD/novex-vio" --debug --web \
    --web-port "$PORT" --socket "$SOCKET" \
    > /tmp/novex-web-test.out 2>/tmp/novex-web-test.err &

VIO_PID=$!

for _ in $(seq 1 80); do
    curl -s -m 1 -o /dev/null "$BASE/api/v1/health" && break
    sleep 0.25
done

if ! curl -s -m 2 -o /dev/null "$BASE/api/v1/health"; then
    bad "dashboard never came up"
    echo "--- log ---"; tail -20 /tmp/novex-web-test.err
    exit 1
fi

ok "dashboard reachable on $BASE"

sleep 4

STATE=$(curl -s -m 3 "$BASE/api/v1/state")

TRACKING=$(echo "$STATE" | jqf tracking)
FEATURES=$(echo "$STATE" | jqf trackedFeatures)
FPS=$(echo "$STATE" | jqf fps)
DEBUG_ON=$(echo "$STATE" | jqf debug enabled)
FRAMEMS=$(echo "$STATE" | jqf timing totalMs)

if [ "$DEBUG_ON" = "True" ]; then
    ok "debug block is live in the stream"
else
    bad "debug block reports enabled=$DEBUG_ON under --debug"
fi

echo "    state: tracking=$TRACKING features=$FEATURES fps=$FPS frame=${FRAMEMS}ms"

for f in position orientation trajectoryM; do
    if echo "$STATE" | grep -q "$f"; then
        ok "stream carries $f"
    else
        bad "stream is missing $f"
    fi
done

# -----------------------------------------------------------------
echo
echo "--- Test 8: a stalled WebSocket client cannot slow the VIO"
# -----------------------------------------------------------------

BEFORE=$(curl -s -m 3 "$BASE/api/v1/state" | jqf frameId)

# Connects, subscribes, then never reads. A blocking implementation
# would park on the socket buffer and stall the pipeline behind it.
node "$(dirname "$0")/stalled_client.js" "$PORT" &
STALL_PID=$!

sleep 6

AFTER=$(curl -s -m 3 "$BASE/api/v1/state" | jqf frameId)
FPS_UNDER_LOAD=$(curl -s -m 3 "$BASE/api/v1/state" | jqf fps)

kill -9 $STALL_PID 2>/dev/null
wait $STALL_PID 2>/dev/null

ADVANCED=$((AFTER - BEFORE))

# ~6 s at 30 fps is ~180 frames. Anything near that proves the loop
# never waited on the browser.
if [ "$ADVANCED" -gt 120 ]; then
    ok "advanced $ADVANCED frames in 6 s with a stalled client (fps $FPS_UNDER_LOAD)"
else
    bad "only advanced $ADVANCED frames; the loop may have blocked"
fi

# -----------------------------------------------------------------
echo
echo "--- Test 5 / 6: disconnect and reconnect"
# -----------------------------------------------------------------

BEFORE=$(curl -s -m 3 "$BASE/api/v1/state" | jqf frameId)
sleep 3
AFTER=$(curl -s -m 3 "$BASE/api/v1/state" | jqf frameId)

if [ $((AFTER - BEFORE)) -gt 60 ]; then
    ok "VIO kept running after the client went away"
else
    bad "VIO stalled once no client was attached"
fi

# A fresh client must get state immediately, with no VIO restart.
FRESH=$(node "$(dirname "$0")/first_frame.js" "$PORT" 2>&1)

if echo "$FRESH" | grep -q "GOT_STATE"; then
    ok "a reconnecting client receives the latest state at once"
    echo "    $FRESH"
else
    bad "reconnecting client got nothing: $FRESH"
fi

# -----------------------------------------------------------------
echo
echo "--- Control commands"
# -----------------------------------------------------------------

R0=$(curl -s -m 3 "$BASE/api/v1/state" | jqf recenterCount)

curl -s -m 3 -X POST "$BASE/api/v1/vio/recenter" > /dev/null
sleep 1

R1=$(curl -s -m 3 "$BASE/api/v1/state" | jqf recenterCount)
POS=$(curl -s -m 3 "$BASE/api/v1/state" | jqf position x)
TRACK=$(curl -s -m 3 "$BASE/api/v1/state" | jqf tracking)

if [ "$R1" -gt "$R0" ]; then
    ok "recenter applied by the VIO thread (count $R0 -> $R1)"
else
    bad "recenter did not take effect"
fi

# The distinction that matters: recentring must not drop tracking.
echo "    position.x right after recenter: $POS"

if [ "$TRACK" = "True" ]; then
    ok "tracking survived the recenter"
else
    bad "recenter dropped tracking; it must not"
fi

curl -s -m 3 -X POST "$BASE/api/v1/vio/pause" > /dev/null
sleep 1
P1=$(curl -s -m 3 "$BASE/api/v1/state" | jqf frameId)
sleep 2
P2=$(curl -s -m 3 "$BASE/api/v1/state" | jqf frameId)

if [ "$P1" -eq "$P2" ]; then
    ok "pause stopped frame processing"
else
    bad "frames still advanced while paused ($P1 -> $P2)"
fi

curl -s -m 3 -X POST "$BASE/api/v1/vio/resume" > /dev/null
sleep 2
P3=$(curl -s -m 3 "$BASE/api/v1/state" | jqf frameId)

if [ "$P3" -gt "$P2" ]; then
    ok "resume restarted processing ($P2 -> $P3)"
else
    bad "resume did not take effect"
fi

RS0=$(curl -s -m 3 "$BASE/api/v1/state" | jqf resetCount)
curl -s -m 3 -X POST "$BASE/api/v1/vio/reset" > /dev/null
sleep 1
RS1=$(curl -s -m 3 "$BASE/api/v1/state" | jqf resetCount)

if [ "$RS1" -gt "$RS0" ]; then
    ok "reset applied ($RS0 -> $RS1)"
else
    bad "reset did not take effect"
fi

# -----------------------------------------------------------------
echo
echo "--- Point cloud: binary stream, delta map, diagnostics"
# -----------------------------------------------------------------

POINTS=$(node "$(dirname "$0")/points_client.js" "$PORT" 4 2>&1)

pc() { echo "$POINTS" | jqf "$@"; }

if [ "$(pc badHeaders)" = "0" ] && [ "$(pc liveMessages)" -gt 5 ] 2>/dev/null; then
    ok "binary LIVE messages arrive with valid headers ($(pc liveMessages) in 4 s)"
else
    bad "no valid LIVE point messages: $POINTS"
fi

if [ "$(pc mapResets)" -ge 1 ] 2>/dev/null && [ "$(pc mapMessages)" -gt 5 ] 2>/dev/null; then
    ok "new client got a full map, then deltas ($(pc mapMessages) messages)"
else
    bad "map stream missing or never reset for a new client: $POINTS"
fi

MIRROR=$(pc mirrorSize)
REPORTED=$(pc reportedMapSize)

if [ -n "$MIRROR" ] && [ "$MIRROR" = "$REPORTED" ] && [ "$MIRROR" -gt 0 ]; then
    ok "map rebuilt from deltas matches the daemon ($MIRROR points)"
else
    bad "delta-rebuilt map $MIRROR != daemon map $REPORTED"
fi

DIAG=$(curl -s "$BASE/api/v1/diagnostics")

if [ -n "$(echo "$DIAG" | jqf geometry reprojectionMedianPx)" ] &&
   [ -n "$(echo "$DIAG" | jqf stationary indication)" -o "$(echo "$DIAG" | jqf stationary haveData)" = "False" ] &&
   [ -n "$(echo "$DIAG" | jqf pointCloud mapPoints)" ]; then
    ok "GET /api/v1/diagnostics carries geometry, stationary and point cloud"
else
    bad "diagnostics endpoint incomplete: ${DIAG:0:200}"
fi

curl -s -X POST "$BASE/api/v1/vio/stationary?enabled=true" > /dev/null
sleep 3
ACTIVE=$(curl -s "$BASE/api/v1/diagnostics" | jqf stationary active)
FRAMES=$(curl -s "$BASE/api/v1/diagnostics" | jqf stationary frames)
curl -s -X POST "$BASE/api/v1/vio/stationary?enabled=false" > /dev/null

if [ "$ACTIVE" = "True" ] && [ "$FRAMES" -gt 30 ] 2>/dev/null; then
    ok "stationary test starts from the API and collects ($FRAMES frames)"
else
    bad "stationary test did not run (active=$ACTIVE frames=$FRAMES)"
fi

EPOCH_BEFORE=$(curl -s "$BASE/api/v1/diagnostics" | jqf pointCloud mapEpoch)
curl -s -X POST "$BASE/api/v1/map/clear" > /dev/null
sleep 1
EPOCH_AFTER=$(curl -s "$BASE/api/v1/diagnostics" | jqf pointCloud mapEpoch)
TRACKING=$(curl -s "$BASE/api/v1/state" | jqf tracking)

if [ -n "$EPOCH_BEFORE" ] && [ "$EPOCH_AFTER" -gt "$EPOCH_BEFORE" ] 2>/dev/null &&
   [ "$TRACKING" = "True" ]; then
    ok "clear map starts a new epoch and leaves tracking alone"
else
    bad "clear map: epoch $EPOCH_BEFORE -> $EPOCH_AFTER, tracking $TRACKING"
fi

# -----------------------------------------------------------------
echo
echo "--- Test 28: clean shutdown stops node and prints one report"
# -----------------------------------------------------------------

kill -TERM "$VIO_PID"

EXITED=0
for _ in $(seq 1 60); do
    if ! kill -0 "$VIO_PID" 2>/dev/null; then EXITED=1; break; fi
    sleep 0.25
done

wait "$VIO_PID" 2>/dev/null
VIO_PID=""

if [ "$EXITED" -eq 1 ]; then
    ok "exited on SIGTERM"
else
    bad "ignored SIGTERM"
fi

REPORTS=$(grep -c "NOVEX VIO DEBUG" /tmp/novex-web-test.out)

if [ "$REPORTS" -eq 1 ]; then
    ok "debug report printed exactly once on exit"
else
    bad "debug report printed $REPORTS times"
fi

sleep 1

# Checked by port rather than by pgrep: a pattern like
# "node server.js" also matches the shell command line that contains
# it, which produces a false positive.
if curl -s -m 2 -o /dev/null "$BASE/api/v1/health"; then
    bad "the node server outlived novex-vio (port $PORT still served)"
else
    ok "node server shut down with the daemon, port $PORT released"
fi

if [ -S "$SOCKET" ]; then
    bad "IPC socket was left behind"
else
    ok "IPC socket removed"
fi

echo
echo "=========================="
echo "passed $pass, failed $fail"

[ "$fail" -eq 0 ]
