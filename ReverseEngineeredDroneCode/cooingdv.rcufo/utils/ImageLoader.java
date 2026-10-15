package com.cooingdv.rcufo.utils;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.text.TextUtils;
import android.util.LruCache;
import com.cooingdv.rcufo.C3033R;

/* JADX INFO: loaded from: classes2.dex */
public class ImageLoader {
    public static final String DEFAULT_PATH = "null";
    private static String TAG = "ImageLoader";
    private static ImageLoader instance;
    private LruCache<String, Bitmap> mImageCache = new LruCache<String, Bitmap>(((int) (Runtime.getRuntime().maxMemory() / 1024)) / 8) { // from class: com.cooingdv.rcufo.utils.ImageLoader.1
        /* JADX INFO: Access modifiers changed from: protected */
        @Override // android.util.LruCache
        public int sizeOf(String str, Bitmap bitmap) {
            return ImageLoader.this.sizeOfBitmap(bitmap);
        }
    };

    /* JADX INFO: Access modifiers changed from: private */
    public int sizeOfBitmap(Bitmap bitmap) {
        return bitmap.getAllocationByteCount() / 1024;
    }

    public static ImageLoader getInstance() {
        if (instance == null) {
            synchronized (ImageLoader.class) {
                if (instance == null) {
                    instance = new ImageLoader();
                }
            }
        }
        return instance;
    }

    public Bitmap loadImage(Context context, String str) {
        if (TextUtils.isEmpty(str)) {
            Bitmap bitmap = this.mImageCache.get("null");
            if (bitmap != null) {
                return bitmap;
            }
            Bitmap bitmapDecodeResource = BitmapFactory.decodeResource(context.getResources(), C3033R.mipmap.ic_default_image);
            this.mImageCache.put("null", bitmapDecodeResource);
            return bitmapDecodeResource;
        }
        Bitmap bitmap2 = this.mImageCache.get(str);
        if (bitmap2 != null) {
            return bitmap2;
        }
        Bitmap bitmapDecodeFile = BitmapFactory.decodeFile(str);
        return bitmapDecodeFile == null ? loadImage(context, null) : bitmapDecodeFile;
    }

    public void clearCache() {
        LruCache<String, Bitmap> lruCache = this.mImageCache;
        if (lruCache != null) {
            lruCache.evictAll();
        }
        System.gc();
    }

    public void release() {
        instance = null;
        clearCache();
    }
}
