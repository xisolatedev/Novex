package com.cooingdv.rcufo.utils;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.os.Environment;
import android.os.StatFs;
import android.text.TextUtils;
import android.util.Log;
import com.cooingdv.rcufo.libs.verticalseekbar.VerticalSeekBar;
import com.cooingdv.rcufo.tools.BufChangeHex;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLEncoder;
import org.objectweb.asm.Opcodes;

/* JADX INFO: loaded from: classes2.dex */
public class BitmapUtil {
    public static final String DIR = "/sdcard/hypers";
    private static int FREE_SD_SPACE_NEEDED_TO_CACHE = 1;

    /* JADX INFO: renamed from: MB */
    private static int f10186MB = 1048576;

    public static Bitmap ReadBitmapById(Context context, int i) {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inPreferredConfig = Bitmap.Config.RGB_565;
        options.inPurgeable = true;
        options.inInputShareable = true;
        return BitmapFactory.decodeStream(context.getResources().openRawResource(i), null, options);
    }

    public static Bitmap ReadBitmapById(Context context, int i, int i2, int i3) {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inPreferredConfig = Bitmap.Config.ARGB_8888;
        options.inInputShareable = true;
        options.inPurgeable = true;
        return getBitmap(BitmapFactory.decodeStream(context.getResources().openRawResource(i), null, options), i2, i3);
    }

    public static Bitmap getBitmap(Bitmap bitmap, int i, int i2) {
        int width = bitmap.getWidth();
        int height = bitmap.getHeight();
        Log.e("jj", "图片宽度" + width + ",screenWidth=" + i);
        Matrix matrix = new Matrix();
        float f = ((float) i) / ((float) width);
        matrix.postScale(f, f);
        return Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, true);
    }

    public static void saveBitmap(String str, Bitmap bitmap) {
        if (BufChangeHex.byte2File(BufChangeHex.Bitmap2Bytes(bitmap), str, null)) {
            Log.i("bitmapUtil", "已经保存：width:" + bitmap.getWidth() + "height:" + bitmap.getHeight());
        }
    }

    public static void saveBmpToSd(Bitmap bitmap, String str, int i) {
        if (FREE_SD_SPACE_NEEDED_TO_CACHE <= freeSpaceOnSd() && "mounted".equals(Environment.getExternalStorageState())) {
            File file = new File(DIR);
            if (!file.exists()) {
                file.mkdirs();
            }
            File file2 = new File("/sdcard/hypers/" + str);
            try {
                file2.createNewFile();
                FileOutputStream fileOutputStream = new FileOutputStream(file2);
                bitmap.compress(Bitmap.CompressFormat.PNG, i, fileOutputStream);
                fileOutputStream.flush();
                fileOutputStream.close();
                Log.e("bitmapUtil", "图片保存成功");
            } catch (FileNotFoundException e) {
                e.printStackTrace();
            } catch (IOException e2) {
                e2.printStackTrace();
            }
        }
    }

    public static Bitmap GetBitmap(String str, int i) {
        if (str == null) {
            return null;
        }
        String strEncode = URLEncoder.encode(str);
        if (Exist("/sdcard/hypers/" + strEncode)) {
            return BitmapFactory.decodeFile("/sdcard/hypers/" + strEncode);
        }
        try {
            InputStream inputStreamOpenStream = new URL(str).openStream();
            Bitmap bitmapDecodeStream = BitmapFactory.decodeStream(inputStreamOpenStream);
            if (bitmapDecodeStream != null) {
                saveBmpToSd(bitmapDecodeStream, strEncode, i);
            }
            inputStreamOpenStream.close();
            return bitmapDecodeStream;
        } catch (Exception e) {
            e.printStackTrace();
            return null;
        }
    }

    public static boolean Exist(String str) {
        return new File(DIR + str).exists();
    }

    private static int freeSpaceOnSd() {
        StatFs statFs = new StatFs(Environment.getExternalStorageDirectory().getPath());
        return (int) ((((double) statFs.getAvailableBlocks()) * ((double) statFs.getBlockSize())) / ((double) f10186MB));
    }

    public static Bitmap rotateBitmap(Bitmap bitmap, float f) {
        if (bitmap == null) {
            return null;
        }
        int width = bitmap.getWidth();
        int height = bitmap.getHeight();
        Matrix matrix = new Matrix();
        matrix.setRotate(f);
        Bitmap bitmapCreateBitmap = Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, false);
        if (bitmapCreateBitmap.equals(bitmap)) {
            return bitmapCreateBitmap;
        }
        bitmap.recycle();
        return bitmapCreateBitmap;
    }

    public static Bitmap compressImage(Bitmap bitmap) {
        ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();
        int i = 100;
        bitmap.compress(Bitmap.CompressFormat.JPEG, 100, byteArrayOutputStream);
        while (byteArrayOutputStream.toByteArray().length / 1024 > 1000) {
            byteArrayOutputStream.reset();
            bitmap.compress(Bitmap.CompressFormat.JPEG, i, byteArrayOutputStream);
            i -= 10;
        }
        return BitmapFactory.decodeStream(new ByteArrayInputStream(byteArrayOutputStream.toByteArray()), null, null);
    }

    /* JADX WARN: Code duplicated, block: B:37:0x0050 A[PHI: r0 r9
      0x0050: PHI (r0v4 float) = (r0v0 float), (r0v1 float), (r0v2 float), (r0v3 float), (r0v11 float) binds: [B:36:0x004e, B:30:0x0042, B:24:0x0036, B:18:0x002a, B:12:0x001e] A[DONT_GENERATE, DONT_INLINE]
      0x0050: PHI (r9v9 float) = (r9v2 float), (r9v4 float), (r9v6 float), (r9v8 float), (r9v17 float) binds: [B:36:0x004e, B:30:0x0042, B:24:0x0036, B:18:0x002a, B:12:0x001e] A[DONT_GENERATE, DONT_INLINE]] */
    /* JADX WARN: Code duplicated, block: B:38:0x0055 A[PHI: r0 r9
      0x0055: PHI (r0v8 float) = (r0v0 float), (r0v1 float), (r0v2 float), (r0v3 float), (r0v11 float) binds: [B:36:0x004e, B:30:0x0042, B:24:0x0036, B:18:0x002a, B:12:0x001e] A[DONT_GENERATE, DONT_INLINE]
      0x0055: PHI (r9v13 float) = (r9v2 float), (r9v4 float), (r9v6 float), (r9v8 float), (r9v17 float) binds: [B:36:0x004e, B:30:0x0042, B:24:0x0036, B:18:0x002a, B:12:0x001e] A[DONT_GENERATE, DONT_INLINE]] */
    /* JADX WARN: Code duplicated, block: B:41:0x0069  */
    public static Bitmap fakeBitmap(Bitmap bitmap, int i, boolean z) {
        float f;
        float f2;
        float f3;
        float f4;
        if (bitmap == null) {
            return null;
        }
        int width = bitmap.getWidth();
        int height = bitmap.getHeight();
        Matrix matrix = new Matrix();
        switch (i) {
            case 1:
                if (height == 480) {
                    return bitmap;
                }
                f = 480.0f;
                f2 = 640.0f;
                if (height > width) {
                    f3 = f / width;
                    f4 = f2 / height;
                } else {
                    float f5 = f2 / width;
                    f4 = f / height;
                    f3 = f5;
                }
                matrix.postScale(f3, f4);
                Bitmap bitmapCreateBitmap = Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, false);
                if (z) {
                    bitmap.recycle();
                }
                return bitmapCreateBitmap;
            case 2:
            case 3:
                if (width == 1280) {
                    return bitmap;
                }
                f = 720.0f;
                f2 = 1280.0f;
                if (height > width) {
                    f3 = f / width;
                    f4 = f2 / height;
                } else {
                    float f6 = f2 / width;
                    f4 = f / height;
                    f3 = f6;
                }
                matrix.postScale(f3, f4);
                Bitmap bitmapCreateBitmap2 = Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, false);
                if (z) {
                    bitmap.recycle();
                }
                return bitmapCreateBitmap2;
            case 4:
                if (width == 1920) {
                    return bitmap;
                }
                f = 1080.0f;
                f2 = 1920.0f;
                if (height > width) {
                    f3 = f / width;
                    f4 = f2 / height;
                } else {
                    float f7 = f2 / width;
                    f4 = f / height;
                    f3 = f7;
                }
                matrix.postScale(f3, f4);
                Bitmap bitmapCreateBitmap3 = Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, false);
                if (z) {
                    bitmap.recycle();
                }
                return bitmapCreateBitmap3;
            case 5:
                if (width == 4096) {
                    return bitmap;
                }
                f = 2160.0f;
                f2 = 4096.0f;
                if (height > width) {
                    f3 = f / width;
                    f4 = f2 / height;
                } else {
                    float f8 = f2 / width;
                    f4 = f / height;
                    f3 = f8;
                }
                matrix.postScale(f3, f4);
                Bitmap bitmapCreateBitmap4 = Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, false);
                if (z) {
                    bitmap.recycle();
                }
                return bitmapCreateBitmap4;
            case 6:
                if (width == 7680) {
                    return bitmap;
                }
                f = 4320.0f;
                f2 = 7680.0f;
                if (height > width) {
                    f3 = f / width;
                    f4 = f2 / height;
                } else {
                    float f9 = f2 / width;
                    f4 = f / height;
                    f3 = f9;
                }
                matrix.postScale(f3, f4);
                Bitmap bitmapCreateBitmap5 = Bitmap.createBitmap(bitmap, 0, 0, width, height, matrix, false);
                if (z) {
                    bitmap.recycle();
                }
                return bitmapCreateBitmap5;
            default:
                return bitmap;
        }
    }

    public static Bitmap getImage(String str, boolean z) {
        int exifOrientation = getExifOrientation(str);
        if (TextUtils.isEmpty(str)) {
            return null;
        }
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(str, options);
        options.inJustDecodeBounds = false;
        int i = options.outWidth;
        int i2 = options.outHeight;
        options.inSampleSize = 1;
        Bitmap bitmapDecodeFile = BitmapFactory.decodeFile(str, options);
        if (exifOrientation == 90 || exifOrientation == 180 || exifOrientation == 270) {
            bitmapDecodeFile = rotateBitmap(bitmapDecodeFile, exifOrientation);
        }
        return z ? bitmapDecodeFile : compressImage(bitmapDecodeFile);
    }

    public static int getExifOrientation(String str) {
        ExifInterface exifInterface;
        int attributeInt;
        try {
            exifInterface = new ExifInterface(str);
        } catch (IOException unused) {
            exifInterface = null;
        }
        if (exifInterface != null && (attributeInt = exifInterface.getAttributeInt("Orientation", -1)) != -1) {
            if (attributeInt == 3) {
                return Opcodes.GETFIELD;
            }
            if (attributeInt == 6) {
                return 90;
            }
            if (attributeInt == 8) {
                return VerticalSeekBar.ROTATION_ANGLE_CW_270;
            }
        }
        return 0;
    }
}
