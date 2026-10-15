package com.cooingdv.rcufo.utils;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.ParcelFileDescriptor;
import android.os.StatFs;
import android.provider.MediaStore;
import android.provider.Settings;
import android.text.TextUtils;
import android.text.format.Formatter;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Window;
import android.view.WindowManager;
import com.cooingdv.rcufo.base.MainApplication;
import com.cooingdv.rcufo.beans.FileInfo;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.tools.TimeFormater;
import com.mbridge.msdk.playercommon.exoplayer2.util.MimeTypes;
import dalvik.system.DexFile;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import org.json.C7610a9;

/* JADX INFO: loaded from: classes2.dex */
public class AppUtils implements IConstants {
    private static final String TAG = "AppUtils";

    public static int dip2px(Context context, float f) {
        return (int) ((f * context.getResources().getDisplayMetrics().density) + 0.5f);
    }

    public static int getScreenWidth(Context context) {
        return ((WindowManager) context.getSystemService("window")).getDefaultDisplay().getWidth();
    }

    public static String getAppStoragePath(MainApplication mainApplication, String str, boolean z) {
        if (mainApplication == null) {
            Dbug.m13285e(TAG, "getAppStoragePath: application is null!");
            return null;
        }
        if (z) {
            return splicingFilePath(mainApplication.getAppName(), mainApplication.getDeviceUUID(), str, "RearView");
        }
        return splicingFilePath(mainApplication.getAppName(), mainApplication.getDeviceUUID(), str, null);
    }

    public static String splicingFilePath(String str, String str2, String str3, String str4) {
        String str5;
        if (!TextUtils.isEmpty(str)) {
            if (Build.VERSION.SDK_INT >= 29 && !Environment.isExternalStorageLegacy()) {
                str5 = ROOT_PATH2;
            } else {
                str5 = ROOT_PATH;
            }
            if (str.contains(File.separator)) {
                for (String str6 : str.split(File.separator)) {
                    if (!TextUtils.isEmpty(str6)) {
                        str5 = str5 + File.separator + str6;
                        File file = new File(str5);
                        if (!file.exists() && file.mkdir()) {
                            Dbug.m13288w(TAG, "create root dir success! path : " + str5);
                        }
                    }
                }
            } else {
                str5 = str5 + File.separator + str;
                File file2 = new File(str5);
                if (!file2.exists() && file2.mkdir()) {
                    Dbug.m13288w(TAG, "create root dir success! path : " + str5);
                }
            }
            if (TextUtils.isEmpty(str2)) {
                return str5;
            }
            String str7 = str5 + File.separator + str2;
            File file3 = new File(str7);
            if (!file3.exists() && file3.mkdir()) {
                Dbug.m13288w(TAG, "create one dir success!");
            }
            if (TextUtils.isEmpty(str3)) {
                return str7;
            }
            String str8 = str7 + File.separator + str3;
            File file4 = new File(str8);
            if (!file4.exists() && file4.mkdir()) {
                Dbug.m13288w(TAG, "create two dir success!");
            }
            if (TextUtils.isEmpty(str4)) {
                return str8;
            }
            String str9 = str8 + File.separator + str4;
            File file5 = new File(str9);
            if (!file5.exists() && file5.mkdir()) {
                Dbug.m13288w(TAG, "create three sub dir success!");
            }
            return str9;
        }
        if (Build.VERSION.SDK_INT >= 29 && !Environment.isExternalStorageLegacy()) {
            return ROOT_PATH2;
        }
        return ROOT_PATH;
    }

    public static void deleteFile(File file) {
        if (file == null || !file.exists()) {
            return;
        }
        if (file.isFile()) {
            if (file.delete()) {
                System.out.printf("delete file success!", new Object[0]);
                return;
            }
            return;
        }
        if (file.isDirectory()) {
            File[] fileArrListFiles = file.listFiles();
            if (fileArrListFiles == null || fileArrListFiles.length == 0) {
                if (file.delete()) {
                    System.out.printf("delete empty file success!", new Object[0]);
                    return;
                }
                return;
            }
            for (File file2 : fileArrListFiles) {
                deleteFile(file2);
            }
            if (file.delete()) {
                System.out.printf("delete empty file success!", new Object[0]);
            }
        }
    }

    public static int judgeFileType(String str) {
        if (TextUtils.isEmpty(str)) {
            return 0;
        }
        if (str.endsWith(".png") || str.endsWith(".PNG") || str.endsWith(".JPEG") || str.endsWith(".jpeg") || str.endsWith(".jpg") || str.endsWith(".JPG")) {
            return 1;
        }
        return (str.endsWith(".mov") || str.endsWith(".MOV") || str.endsWith(".mp4") || str.endsWith(".MP4") || str.endsWith(".avi") || str.endsWith(".AVI")) ? 2 : 0;
    }

    private static String[] sort(String[] strArr) {
        if (strArr == null || strArr.length == 0) {
            return strArr;
        }
        int length = strArr.length;
        double[] dArr = new double[length];
        for (int i = 0; i < length; i++) {
            try {
                dArr[i] = Double.valueOf(strArr[i]).doubleValue();
            } catch (NumberFormatException e) {
                e.printStackTrace();
            }
        }
        return sort(dArr);
    }

    private static String[] sort(double[] dArr) {
        if (dArr == null || dArr.length == 0) {
            return null;
        }
        for (int i = 0; i < dArr.length; i++) {
            int i2 = 0;
            while (i2 < (dArr.length - i) - 1) {
                double d = dArr[i2];
                int i3 = i2 + 1;
                double d2 = dArr[i3];
                if (d < d2) {
                    dArr[i2] = d2;
                    dArr[i3] = d;
                }
                i2 = i3;
            }
        }
        int length = dArr.length;
        String[] strArr = new String[length];
        for (int i4 = 0; i4 < length; i4++) {
            strArr[i4] = String.valueOf(dArr[i4]);
        }
        return strArr;
    }

    private static String[] parseDeviceVersionInfo(String str) {
        if (TextUtils.isEmpty(str)) {
            return null;
        }
        if (str.contains(C7610a9.i.f11604d)) {
            str = str.replace(C7610a9.i.f11604d, "");
        }
        if (str.contains(C7610a9.i.f11606e)) {
            str = str.replace(C7610a9.i.f11606e, "");
        }
        if (str.contains("\"")) {
            str = str.replace("\"", "");
        }
        if (str.contains(",")) {
            return str.split(",");
        }
        return new String[]{str};
    }

    public static String getFromRaw(Context context, int i) {
        if (context == null) {
            return "";
        }
        InputStream inputStreamOpenRawResource = null;
        try {
            inputStreamOpenRawResource = context.getResources().openRawResource(i);
            byte[] bArr = new byte[inputStreamOpenRawResource.available()];
            inputStreamOpenRawResource.read(bArr);
            return new String(bArr, "GBK");
        } catch (Exception e) {
            e.printStackTrace();
            if (inputStreamOpenRawResource != null) {
                try {
                    return "";
                } catch (IOException e2) {
                    return "";
                }
            }
            return "";
        } finally {
            if (inputStreamOpenRawResource != null) {
                try {
                    inputStreamOpenRawResource.close();
                } catch (IOException e3) {
                    e3.printStackTrace();
                }
            }
        }
    }

    public static List<FileInfo> getAllLocalFile(String str, String str2, boolean z) {
        if (TextUtils.isEmpty(str)) {
            return null;
        }
        ArrayList arrayList = new ArrayList();
        try {
            File file = new File(str);
            if (file.exists() && file.isDirectory()) {
                for (File file2 : file.listFiles()) {
                    if (file2.isDirectory()) {
                        for (File file3 : file2.listFiles()) {
                            if (file3.getName().equals(str2)) {
                                arrayList.addAll(getLocalFileInfo(file3.getPath(), z));
                            }
                        }
                    } else {
                        FileInfo fileInfo = new FileInfo();
                        if (z) {
                            fileInfo.setFilename(getFileName(file2.getName()));
                            fileInfo.setDirectory(false);
                            fileInfo.setSize(file2.length());
                            fileInfo.setCreateDate(getFileCreateTime(file2.getName()));
                            fileInfo.setPath(file2.getAbsolutePath());
                            fileInfo.setFileType(IConstants.BROWSE_LOCAL_MODE);
                        } else {
                            String formatedDateTime = TimeFormater.getFormatedDateTime(TimeFormater.yyyyMMddHHmmss, file2.lastModified());
                            if (formatedDateTime == null) {
                                formatedDateTime = "2015-08-07 15:34:26";
                            }
                            fileInfo.setFilename(file2.getName());
                            fileInfo.setDirectory(file2.isDirectory());
                            fileInfo.setSize(file2.length());
                            fileInfo.setCreateDate(formatedDateTime);
                            fileInfo.setPath(file2.getAbsolutePath());
                            fileInfo.setFileType(IConstants.BROWSE_RECORD_MODE);
                        }
                        arrayList.add(fileInfo);
                    }
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        Collections.sort(arrayList, new Comparator<FileInfo>() { // from class: com.cooingdv.rcufo.utils.AppUtils.1
            @Override // java.util.Comparator
            public int compare(FileInfo fileInfo2, FileInfo fileInfo3) {
                return fileInfo3.getFilename().compareTo(fileInfo2.getFilename());
            }
        });
        return arrayList;
    }

    public static List<FileInfo> getLocalFileInfo(String str, boolean z) {
        File file;
        ArrayList arrayList = new ArrayList();
        if (str != null && !str.isEmpty()) {
            try {
                File file2 = new File(str);
                if (file2.exists() && file2.isDirectory()) {
                    File[] fileArrListFiles = file2.listFiles();
                    HashMap map = new HashMap();
                    ArrayList arrayList2 = new ArrayList();
                    if (fileArrListFiles != null && fileArrListFiles.length > 0) {
                        for (File file3 : fileArrListFiles) {
                            if (file3.isFile()) {
                                if (z) {
                                    String name = file3.getName();
                                    if (!TextUtils.isEmpty(name)) {
                                        arrayList2.add(name);
                                        map.put(name, file3);
                                    }
                                } else {
                                    String str2 = file3.lastModified() + "";
                                    arrayList2.add(str2);
                                    map.put(str2, file3);
                                }
                            }
                        }
                        for (String str3 : descSort((String[]) arrayList2.toArray(new String[arrayList2.size()]))) {
                            if (!TextUtils.isEmpty(str3) && (file = (File) map.get(str3)) != null) {
                                FileInfo fileInfo = new FileInfo();
                                if (z) {
                                    if (file.isFile() && str3.equals(file.getName())) {
                                        fileInfo.setFilename(getFileName(file.getName()));
                                        fileInfo.setDirectory(false);
                                        fileInfo.setSize(file.length());
                                        fileInfo.setCreateDate(getFileCreateTime(file.getName()));
                                        fileInfo.setPath(file.getAbsolutePath());
                                        fileInfo.setFileType(IConstants.BROWSE_LOCAL_MODE);
                                    }
                                } else if (file.isFile()) {
                                    if (str3.equals(file.lastModified() + "")) {
                                        String formatedDateTime = TimeFormater.getFormatedDateTime(TimeFormater.yyyyMMddHHmmss, file.lastModified());
                                        if (formatedDateTime == null) {
                                            formatedDateTime = "2015-08-07 15:34:26";
                                        }
                                        fileInfo.setFilename(file.getName());
                                        fileInfo.setDirectory(false);
                                        fileInfo.setSize(file.length());
                                        fileInfo.setCreateDate(formatedDateTime);
                                        fileInfo.setPath(file.getAbsolutePath());
                                        fileInfo.setFileType(IConstants.BROWSE_RECORD_MODE);
                                    }
                                }
                                arrayList.add(fileInfo);
                            }
                        }
                    }
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
        }
        return arrayList;
    }

    private static String[] descSort(String[] strArr) {
        if (strArr != null && strArr.length != 0) {
            for (int i = 0; i < strArr.length; i++) {
                int i2 = 0;
                while (i2 < (strArr.length - i) - 1) {
                    int i3 = i2 + 1;
                    if (strArr[i2].compareTo(strArr[i3]) < 0) {
                        String str = strArr[i2];
                        strArr[i2] = strArr[i3];
                        strArr[i3] = str;
                    }
                    i2 = i3;
                }
            }
        }
        return strArr;
    }

    public static void descSort(List<String> list) {
        if (list == null || list.size() <= 0) {
            return;
        }
        Collections.sort(list, new Comparator<String>() { // from class: com.cooingdv.rcufo.utils.AppUtils.2
            @Override // java.util.Comparator
            public int compare(String str, String str2) {
                if (str.compareTo(str2) > 0) {
                    return -1;
                }
                return str.compareTo(str2) < 0 ? 1 : 0;
            }
        });
    }

    private static String getFileName(String str) {
        String strSubstring;
        if (!TextUtils.isEmpty(str)) {
            if (!str.contains(".")) {
                strSubstring = "";
            } else {
                strSubstring = str.substring(str.indexOf("."));
            }
            String str2 = str.contains("_") ? str.split("_")[0] : null;
            if (!TextUtils.isEmpty(str2)) {
                return str2 + strSubstring;
            }
        }
        return null;
    }

    private static String getFileCreateTime(String str) {
        if (TextUtils.isEmpty(str) || !str.contains("_")) {
            return null;
        }
        String[] strArrSplit = str.split("_");
        if (strArrSplit[1].length() < 14) {
            return null;
        }
        String str2 = strArrSplit[1];
        return str2.substring(0, 4) + "-" + str2.substring(4, 6) + "-" + str2.substring(6, 8) + " " + str2.substring(8, 10) + ":" + str2.substring(10, 12) + ":" + str2.substring(12, 14);
    }

    /* JADX WARN: Not initialized variable reg: 6, insn: 0x0532: RETURN (r6 I:boolean) A[SYNTHETIC], block:B:332:? */
    /*  JADX ERROR: Type inference failed
        jadx.core.utils.exceptions.JadxOverflowException: Type inference error: updates count limit reached with updateSeq = 13391. Try increasing type updates limit count.
        	at jadx.core.utils.ErrorsCounter.addError(ErrorsCounter.java:59)
        	at jadx.core.utils.ErrorsCounter.error(ErrorsCounter.java:31)
        	at jadx.core.dex.attributes.nodes.NotificationAttrNode.addError(NotificationAttrNode.java:19)
        	at jadx.core.dex.visitors.typeinference.TypeInferenceVisitor.visit(TypeInferenceVisitor.java:79)
        */
    public static boolean getRecordVideoThumb(com.cooingdv.rcufo.beans.FileInfo r39, java.lang.String r40) {
        /*
            Method dump skipped, instruction units count: 1339
            To view this dump change 'Code comments level' option to 'DEBUG'
        */
        throw new UnsupportedOperationException("Method not decompiled: com.cooingdv.rcufo.utils.AppUtils.getRecordVideoThumb(com.cooingdv.rcufo.beans.FileInfo, java.lang.String):boolean");
    }

    public static Locale getLanguage(int i) {
        switch (i) {
            case 0:
                return Locale.SIMPLIFIED_CHINESE;
            case 1:
                return Locale.US;
            case 2:
                return Locale.FRENCH;
            case 3:
                return Locale.GERMAN;
            case 4:
                return Locale.JAPAN;
            case 5:
                return new Locale("es", "");
            case 6:
                return new Locale("pt", "");
            case 7:
                return Locale.ITALIAN;
            default:
                Dbug.m13285e(TAG, "Unknown language flag" + i);
                return null;
        }
    }

    public static void setLanguage(Context context, Locale locale) {
        Resources resources = context.getApplicationContext().getResources();
        DisplayMetrics displayMetrics = resources.getDisplayMetrics();
        Configuration configuration = resources.getConfiguration();
        if (locale != null) {
            configuration.setLocale(locale);
            if (Build.VERSION.SDK_INT >= 24) {
                AppUtils$$ExternalSyntheticApiModelOutline0.m13281m();
                configuration.setLocales(AppUtils$$ExternalSyntheticApiModelOutline0.m13280m(new Locale[]{locale}));
                context.createConfigurationContext(configuration);
            } else {
                Locale.setDefault(locale);
                resources.updateConfiguration(configuration, displayMetrics);
            }
        }
    }

    public static Context attachBaseContext(Context context) {
        return Build.VERSION.SDK_INT >= 24 ? updateResources(context) : context;
    }

    private static Context updateResources(Context context) {
        Resources resources = context.getResources();
        Locale language = getLanguage(PreferencesHelper.getSharedPreferences(context.getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(context)));
        Configuration configuration = resources.getConfiguration();
        configuration.setLocale(language);
        AppUtils$$ExternalSyntheticApiModelOutline0.m13281m();
        configuration.setLocales(AppUtils$$ExternalSyntheticApiModelOutline0.m13280m(new Locale[]{language}));
        return context.createConfigurationContext(configuration);
    }

    public static Bitmap reverseBitmap(Bitmap bitmap, int i) {
        Matrix matrix;
        if (bitmap == null) {
            return null;
        }
        Canvas canvas = new Canvas();
        Bitmap bitmapCreateBitmap = Bitmap.createBitmap(bitmap.getWidth(), bitmap.getHeight(), Bitmap.Config.ARGB_8888);
        canvas.setBitmap(bitmapCreateBitmap);
        if (i == 0) {
            matrix = new Matrix();
            matrix.postScale(1.0f, -1.0f);
            matrix.postTranslate(0.0f, bitmap.getHeight());
        } else if (i != 1) {
            matrix = null;
        } else {
            matrix = new Matrix();
            matrix.postScale(-1.0f, 1.0f);
            matrix.postTranslate(bitmap.getWidth(), 0.0f);
        }
        if (matrix == null) {
            return bitmap;
        }
        canvas.drawBitmap(bitmap, matrix, null);
        return bitmapCreateBitmap;
    }

    public static Bitmap rotateBitmap(int i, Bitmap bitmap) {
        if (bitmap == null) {
            return null;
        }
        Matrix matrix = new Matrix();
        matrix.postRotate(i);
        Bitmap bitmapCreateBitmap = Bitmap.createBitmap(bitmap, 0, 0, bitmap.getWidth(), bitmap.getHeight(), matrix, true);
        if (bitmapCreateBitmap != bitmap && !bitmap.isRecycled()) {
            bitmap.recycle();
        }
        return bitmapCreateBitmap;
    }

    public static int getScreenBrightness(Activity activity) {
        if (activity != null) {
            return Settings.System.getInt(activity.getContentResolver(), "screen_brightness", 125);
        }
        return 125;
    }

    public static void setBrightness(Activity activity, int i) {
        Window window;
        WindowManager.LayoutParams attributes;
        if (activity == null || (window = activity.getWindow()) == null || (attributes = window.getAttributes()) == null) {
            return;
        }
        attributes.screenBrightness = i / 255.0f;
        window.setAttributes(attributes);
        Settings.System.putInt(activity.getContentResolver(), "screen_brightness", i);
    }

    public static int getScreenHeight(Context context) {
        return ((WindowManager) context.getSystemService("window")).getDefaultDisplay().getHeight();
    }

    public static String getSDTotalSize(Context context) {
        StatFs statFs = new StatFs(Environment.getExternalStorageDirectory().getPath());
        return Formatter.formatFileSize(context, ((long) statFs.getBlockSize()) * ((long) statFs.getBlockCount()));
    }

    public static String getSDAvailableSize(Context context) {
        StatFs statFs = new StatFs(Environment.getExternalStorageDirectory().getPath());
        return Formatter.formatFileSize(context, ((long) statFs.getBlockSize()) * ((long) statFs.getAvailableBlocks()));
    }

    public static List<String> getClassName(String str, Context context) {
        ArrayList arrayList = new ArrayList();
        try {
            Enumeration<String> enumerationEntries = new DexFile(context.getPackageCodePath()).entries();
            while (enumerationEntries.hasMoreElements()) {
                String strNextElement = enumerationEntries.nextElement();
                if (strNextElement.contains(str)) {
                    arrayList.add(strNextElement);
                }
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
        return arrayList;
    }

    public static boolean isNumeric(String str) {
        return Pattern.compile("[0-9]*").matcher(str).matches();
    }

    public static boolean isNotSupport4K() {
        String str = Build.MODEL;
        if (str == null || str.length() <= 0) {
            return false;
        }
        String lowerCase = str.toLowerCase();
        Dbug.m13286i("MODEL", "phone_type: " + lowerCase);
        return lowerCase.contains("vivo") && lowerCase.contains("y75");
    }

    public static void mediaScanImage(Context context, File file) {
        try {
            Log.v("mediaScanImage", "file was scanned successfully: " + saveBitmap(context, BitmapFactory.decodeFile(file.getAbsolutePath()), Bitmap.CompressFormat.JPEG, "image/jpeg", file.getName()));
        } catch (Exception e) {
            e.printStackTrace();
            Log.w("mediaScanImage", "file was scanned failed");
        }
    }

    public static void mediaScanVideo(Context context, File file) {
        try {
            Log.v("mediaScanVideo", "file was scanned successfully: " + saveVideo(context, file.getAbsolutePath(), MimeTypes.VIDEO_MP4, file.getName()));
        } catch (Exception e) {
            e.printStackTrace();
            Log.w("mediaScanVideo", "file was scanned failed");
        }
    }

    public static Uri saveBitmap(Context context, Bitmap bitmap, Bitmap.CompressFormat compressFormat, String str, String str2) throws IOException {
        Uri uriInsert;
        ContentValues contentValues = new ContentValues();
        contentValues.put("_display_name", str2);
        contentValues.put("mime_type", str);
        if (Build.VERSION.SDK_INT >= 29) {
            contentValues.put("relative_path", Environment.DIRECTORY_PICTURES);
        } else {
            contentValues.put("_data", Environment.getExternalStorageDirectory().getPath() + File.separator + Environment.DIRECTORY_PICTURES + File.separator + str2);
        }
        ContentResolver contentResolver = context.getContentResolver();
        try {
            uriInsert = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, contentValues);
            try {
                if (uriInsert == null) {
                    throw new IOException("Failed to create new MediaStore record.");
                }
                OutputStream outputStreamOpenOutputStream = contentResolver.openOutputStream(uriInsert);
                try {
                    if (outputStreamOpenOutputStream == null) {
                        throw new IOException("Failed to open output stream.");
                    }
                    if (!bitmap.compress(compressFormat, 100, outputStreamOpenOutputStream)) {
                        throw new IOException("Failed to save bitmap.");
                    }
                    if (outputStreamOpenOutputStream != null) {
                        outputStreamOpenOutputStream.close();
                    }
                    return uriInsert;
                } catch (Throwable th) {
                    if (outputStreamOpenOutputStream != null) {
                        try {
                            outputStreamOpenOutputStream.close();
                        } catch (Throwable th2) {
                            th.addSuppressed(th2);
                        }
                    }
                    throw th;
                }
            } catch (IOException e) {
                e = e;
                if (uriInsert != null) {
                    contentResolver.delete(uriInsert, null, null);
                }
                throw e;
            }
        } catch (IOException e2) {
            e = e2;
            uriInsert = null;
        }
    }

    public static Uri saveVideo(Context context, String str, String str2, String str3) throws IOException {
        Uri uriInsert;
        ContentResolver contentResolver = context.getContentResolver();
        ContentValues contentValues = new ContentValues();
        contentValues.put("title", str3);
        contentValues.put("_display_name", str3);
        contentValues.put("mime_type", str2);
        contentValues.put("date_added", Long.valueOf(System.currentTimeMillis() / 1000));
        if (Build.VERSION.SDK_INT >= 29) {
            contentValues.put("relative_path", Environment.DIRECTORY_MOVIES);
            uriInsert = contentResolver.insert(MediaStore.Video.Media.getContentUri("external_primary"), contentValues);
        } else {
            contentValues.put("_data", context.getExternalMediaDirs()[0] + File.separator + str3);
            uriInsert = contentResolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, contentValues);
        }
        if (Build.VERSION.SDK_INT >= 29) {
            contentValues.put("datetaken", Long.valueOf(System.currentTimeMillis()));
            contentValues.put("is_pending", (Integer) 1);
        }
        try {
            ParcelFileDescriptor parcelFileDescriptorOpenFileDescriptor = contentResolver.openFileDescriptor(uriInsert, "w");
            FileOutputStream fileOutputStream = new FileOutputStream(parcelFileDescriptorOpenFileDescriptor.getFileDescriptor());
            FileInputStream fileInputStream = new FileInputStream(new File(str));
            byte[] bArr = new byte[8192];
            while (true) {
                int i = fileInputStream.read(bArr);
                if (i <= 0) {
                    break;
                }
                fileOutputStream.write(bArr, 0, i);
            }
            fileOutputStream.close();
            fileInputStream.close();
            parcelFileDescriptorOpenFileDescriptor.close();
            if (Build.VERSION.SDK_INT >= 29) {
                contentValues.clear();
                contentValues.put("is_pending", (Integer) 0);
                contentResolver.update(uriInsert, contentValues, null, null);
            }
            return uriInsert;
        } catch (IOException e) {
            if (uriInsert != null) {
                contentResolver.delete(uriInsert, null, null);
            }
            throw e;
        }
    }

    public static String getVideoDirPath(Context context) {
        String videoPath = getVideoPath(context);
        if (videoPath == null) {
            return null;
        }
        File file = new File(videoPath);
        if (file.exists() || file.mkdirs()) {
            return file.getAbsolutePath();
        }
        return null;
    }

    public static String getPhotoDirPath(Context context) {
        String photoPath = getPhotoPath(context);
        if (photoPath == null) {
            return null;
        }
        File file = new File(photoPath);
        if (file.exists() || file.mkdirs()) {
            return file.getAbsolutePath();
        }
        return null;
    }

    public static String getPhotoPath(Context context) {
        return context.getExternalFilesDir(Environment.DIRECTORY_PICTURES).getAbsolutePath();
    }

    public static String getVideoPath(Context context) {
        return context.getExternalFilesDir(Environment.DIRECTORY_MOVIES).getAbsolutePath();
    }

    public static String getDocumentsPath(Context context) {
        return context.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS).getAbsolutePath();
    }

    public static String getThumbPath(Context context) {
        return context.getExternalFilesDir(IConstants.THUMB).getAbsolutePath();
    }

    public static String getPhotoFileName() {
        return "JPG_" + TimeFormater.formatYMD_HMS(System.currentTimeMillis()) + ".jpg";
    }

    public static String getVideoFileName() {
        return "/REC_" + (System.currentTimeMillis() / 1000) + "_0";
    }

    /* JADX WARN: Can't fix incorrect switch cases order, some code will duplicate */
    /* JADX WARN: Code duplicated, block: B:40:0x0085 A[RETURN] */
    public static boolean isSoftEncode(int i) {
        String str;
        if (Build.VERSION.SDK_INT >= 27 && (str = Build.MANUFACTURER) != null && str.length() > 0) {
            String lowerCase = str.toLowerCase();
            Dbug.m13286i("manufacturer", "phone_type: " + lowerCase);
            lowerCase.hashCode();
            switch (lowerCase) {
                case "huawei":
                case "honor":
                case "samsung":
                    if (i == 2048) {
                        return true;
                    }
                    break;
                case "oppo":
                    if (Build.MODEL.equals("PFUM10")) {
                        return true;
                    }
                    break;
                case "vivo":
                    return true;
                case "hi nova":
                    if (Build.MODEL.equals("FIO-BD00")) {
                        return true;
                    }
                    break;
            }
        }
        return false;
    }
}
