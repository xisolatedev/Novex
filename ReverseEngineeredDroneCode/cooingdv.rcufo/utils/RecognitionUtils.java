package com.cooingdv.rcufo.utils;

/* JADX INFO: loaded from: classes2.dex */
public class RecognitionUtils {
    public static native int[] nativeGestureRecognition();

    static {
        System.loadLibrary("lib_gesture");
    }

    public static int[] gestureRecognition() {
        return nativeGestureRecognition();
    }
}
