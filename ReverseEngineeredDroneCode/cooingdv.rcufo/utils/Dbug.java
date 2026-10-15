package com.cooingdv.rcufo.utils;

import android.util.Log;

/* JADX INFO: loaded from: classes2.dex */
public class Dbug {

    /* JADX INFO: renamed from: a */
    private static boolean f10187a = true;

    public static void openOrCloseDebug(boolean z) {
        f10187a = z;
    }

    /* JADX INFO: renamed from: v */
    public static void m13287v(String str, String str2) {
        if (f10187a) {
            Log.v(str, str2);
        }
    }

    /* JADX INFO: renamed from: d */
    public static void m13284d(String str, String str2) {
        if (f10187a) {
            Log.d(str, str2);
        }
    }

    /* JADX INFO: renamed from: i */
    public static void m13286i(String str, String str2) {
        if (f10187a) {
            Log.i(str, str2);
        }
    }

    /* JADX INFO: renamed from: w */
    public static void m13288w(String str, String str2) {
        if (f10187a) {
            Log.w(str, str2);
        }
    }

    /* JADX INFO: renamed from: e */
    public static void m13285e(String str, String str2) {
        if (f10187a) {
            Log.e(str, str2);
        }
    }
}
