package com.cooingdv.rcufo.libs.pullrefreshview.support.utils;

/* JADX INFO: loaded from: classes2.dex */
public class Utils {
    public static final boolean isClassExists(String str) {
        try {
            Class.forName(str);
            return true;
        } catch (ClassNotFoundException unused) {
            return false;
        }
    }
}
