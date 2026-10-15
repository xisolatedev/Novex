package com.cooingdv.rcufo.utils;

import android.content.Context;
import android.os.Environment;
import android.os.StatFs;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

/* JADX INFO: loaded from: classes2.dex */
public class StorageUtil {
    private static final int JELLY_BEAN_MR2 = 18;

    public static long getSdCardFreeBytes() {
        StatFs statFs = new StatFs(Environment.getExternalStorageDirectory().getAbsolutePath());
        return statFs.getAvailableBlocksLong() * statFs.getBlockSizeLong();
    }

    public static long getSdCardUsedBytes() {
        StatFs statFs = new StatFs(Environment.getExternalStorageDirectory().getAbsolutePath());
        return (statFs.getBlockCountLong() - statFs.getAvailableBlocksLong()) * statFs.getBlockSizeLong();
    }

    public static long getSdCardTotalBytes() {
        StatFs statFs = new StatFs(Environment.getExternalStorageDirectory().getAbsolutePath());
        return statFs.getBlockCountLong() * statFs.getBlockSizeLong();
    }

    public static void copyFilesFromRaw(Context context, int i, String str, String str2) {
        InputStream inputStreamOpenRawResource = context.getResources().openRawResource(i);
        File file = new File(str2);
        if (!file.exists()) {
            file.mkdirs();
        }
        readInputStream(str2 + File.separator + str, inputStreamOpenRawResource);
    }

    public static void readInputStream(String str, InputStream inputStream) {
        File file = new File(str);
        try {
            if (file.exists()) {
                return;
            }
            FileOutputStream fileOutputStream = new FileOutputStream(file);
            byte[] bArr = new byte[inputStream.available()];
            while (true) {
                int i = inputStream.read(bArr);
                if (i != -1) {
                    fileOutputStream.write(bArr, 0, i);
                } else {
                    fileOutputStream.flush();
                    fileOutputStream.close();
                    inputStream.close();
                    return;
                }
            }
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        } catch (IOException e2) {
            e2.printStackTrace();
        }
    }

    public static long getFreeDiskSpace() {
        String rootPath = getRootPath();
        if (rootPath != null) {
            return new File(rootPath).getFreeSpace();
        }
        return 0L;
    }

    public static String getRootPath() {
        try {
            return Environment.getExternalStorageDirectory().getCanonicalPath();
        } catch (Exception e) {
            e.printStackTrace();
            return null;
        }
    }
}
