package com.cooingdv.rcufo.utils;

import android.content.Context;
import com.mbridge.msdk.foundation.download.core.DownloadCommon;

/* JADX INFO: loaded from: classes2.dex */
public class LocalUtil {
    public static int getLocaleLanguage(Context context) {
        String language = context.getResources().getConfiguration().locale.getLanguage();
        if (language.endsWith("zh")) {
            return 0;
        }
        if (language.endsWith("fr")) {
            return 2;
        }
        if (language.endsWith(DownloadCommon.DOWNLOAD_REPORT_DOWNLOAD_ERROR)) {
            return 3;
        }
        if (language.endsWith("ja")) {
            return 4;
        }
        if (language.endsWith("es")) {
            return 5;
        }
        if (language.endsWith("pt")) {
            return 6;
        }
        return language.endsWith("it") ? 7 : 1;
    }
}
