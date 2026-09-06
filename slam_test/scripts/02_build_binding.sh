#!/usr/bin/env bash
# ============================================================
# NOVEX - build the Python extension module for ORB-SLAM3
# ============================================================
#   bash scripts/02_build_binding.sh
#
# Produces src/novex_orbslam3.*.so, which main.py imports.
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="$HERE/third_party/install"
VENV="${NOVEX_VENV:-$(cd "$HERE/.." && pwd)/.venv}"

if [ ! -x "$VENV/bin/python" ]; then
    echo "ERROR: no virtualenv at $VENV"
    echo "Create one and install requirements:"
    echo "    python3 -m venv .venv"
    echo "    .venv/bin/pip install -r slam_test/requirements.txt"
    exit 1
fi

PY="$VENV/bin/python"

echo "Python : $PY ($($PY -V))"

# pybind11 ships its own CMake config; ask the interpreter where it is.
PYBIND_DIR="$($PY -c 'import pybind11; print(pybind11.get_cmake_dir())' 2>/dev/null || true)"
if [ -z "$PYBIND_DIR" ]; then
    echo "ERROR: pybind11 is not installed in the virtualenv."
    echo "    $VENV/bin/pip install -r $HERE/requirements.txt"
    exit 1
fi
echo "pybind11: $PYBIND_DIR"

cmake -S "$HERE/native" -B "$HERE/native/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$PREFIX;$PYBIND_DIR" \
    -DPython_EXECUTABLE="$PY" \
    -DPYTHON_EXECUTABLE="$PY"

cmake --build "$HERE/native/build" -j"$(nproc)"

# Put the module next to the Python sources that import it.
cp -v "$HERE/native/build"/novex_orbslam3*.so "$HERE/src/"

echo
echo "=============================================="
echo " BINDING BUILT"
echo "=============================================="
cd "$HERE/src" && "$PY" -c "
import novex_orbslam3 as m
print('module   :', m.__file__)
print('states   :', [s for s in dir(m.TrackingState) if s.isupper()])
print('StereoSlam methods:', [x for x in dir(m.StereoSlam) if not x.startswith('_')])
print()
print('import OK - the module loaded and linked against libORB_SLAM3.so')
"
