package com.cooingdv.rcufo.tools;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.text.TextUtils;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.SoftReference;
import java.util.Hashtable;

/* JADX INFO: loaded from: classes2.dex */
public class BitmapCache implements IConstants {
    private static BitmapCache cache;
    private Hashtable bitmapRefs = new Hashtable();
    private ReferenceQueue queue = new ReferenceQueue();

    class BitmapRef extends SoftReference {
        String _key;

        public BitmapRef(Bitmap bitmap, ReferenceQueue referenceQueue, String str) {
            super(bitmap, referenceQueue);
            this._key = str;
        }
    }

    private BitmapCache() {
    }

    public static BitmapCache getInstance() {
        if (cache == null) {
            cache = new BitmapCache();
        }
        return cache;
    }

    public void addCacheBitmap(Bitmap bitmap, String str) {
        cleanCache();
        this.bitmapRefs.put(str, new BitmapRef(bitmap, this.queue, str));
    }

    public Bitmap getBitmap(String str) {
        if (TextUtils.isEmpty(str)) {
            return null;
        }
        Bitmap bitmap = this.bitmapRefs.contains(str) ? (Bitmap) ((BitmapRef) this.bitmapRefs.get(str)).get() : null;
        if (bitmap != null) {
            return bitmap;
        }
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = false;
        options.inSampleSize = 4;
        Bitmap bitmapDecodeFile = BitmapFactory.decodeFile(str, options);
        addCacheBitmap(bitmapDecodeFile, str);
        return bitmapDecodeFile;
    }

    public int getCount() {
        return this.bitmapRefs.size();
    }

    private void cleanCache() {
        while (true) {
            BitmapRef bitmapRef = (BitmapRef) this.queue.poll();
            if (bitmapRef == null) {
                return;
            } else {
                this.bitmapRefs.remove(bitmapRef._key);
            }
        }
    }

    public void clearCache() {
        cleanCache();
        this.bitmapRefs.clear();
        cache = null;
        System.gc();
        System.runFinalization();
    }
}
