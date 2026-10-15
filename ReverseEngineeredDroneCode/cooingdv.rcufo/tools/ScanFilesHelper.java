package com.cooingdv.rcufo.tools;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.FileUtils;
import android.provider.MediaStore;
import android.text.TextUtils;
import com.cooingdv.rcufo.utils.Dbug;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URLConnection;

/* JADX INFO: loaded from: classes2.dex */
public class ScanFilesHelper implements MediaScannerConnection.MediaScannerConnectionClient {
    private Context mContext;
    private String mFilePath;
    private MediaScannerConnection mMediaScannerConnection;

    public ScanFilesHelper(Context context) {
        this.mContext = context;
        if (this.mMediaScannerConnection == null) {
            this.mMediaScannerConnection = new MediaScannerConnection(context, this);
        }
    }

    private void scanFile(String str) {
        MediaScannerConnection mediaScannerConnection;
        if (TextUtils.isEmpty(str) || (mediaScannerConnection = this.mMediaScannerConnection) == null || !mediaScannerConnection.isConnected()) {
            return;
        }
        Dbug.m13285e("ScanFilesHelper", "scan file absolutePath = " + str);
        File file = new File(str);
        if (file.exists()) {
            if (file.isFile()) {
                this.mMediaScannerConnection.scanFile(file.getAbsolutePath(), null);
                return;
            }
            if (file.listFiles() == null) {
                return;
            }
            for (File file2 : file.listFiles()) {
                if (file2 != null) {
                    scanFile(file2.getAbsolutePath());
                }
            }
        }
    }

    public void updateToDeleteFile(String str) {
        MediaScannerConnection.scanFile(this.mContext, new String[]{str}, null, null);
    }

    public void scanFiles(String str) {
        this.mFilePath = str;
        if (Build.VERSION.SDK_INT >= 29 && !Environment.isExternalStorageLegacy()) {
            new Thread(new Runnable() { // from class: com.cooingdv.rcufo.tools.ScanFilesHelper.1
                @Override // java.lang.Runnable
                public void run() {
                    Uri uriInsert;
                    File file = new File(ScanFilesHelper.this.mFilePath);
                    String mimeType = ScanFilesHelper.getMimeType(file);
                    String name = file.getName();
                    if (file.exists()) {
                        ContentValues contentValues = new ContentValues();
                        contentValues.put("_display_name", name);
                        contentValues.put("mime_type", mimeType);
                        contentValues.put("relative_path", Environment.DIRECTORY_DCIM);
                        ContentResolver contentResolver = ScanFilesHelper.this.mContext.getContentResolver();
                        if (ScanFilesHelper.this.mFilePath.endsWith(".mp4")) {
                            uriInsert = contentResolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, contentValues);
                        } else {
                            uriInsert = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, contentValues);
                        }
                        if (uriInsert == null) {
                            return;
                        }
                        try {
                            OutputStream outputStreamOpenOutputStream = contentResolver.openOutputStream(uriInsert);
                            FileInputStream fileInputStream = new FileInputStream(file);
                            FileUtils.copy(fileInputStream, outputStreamOpenOutputStream);
                            fileInputStream.close();
                            outputStreamOpenOutputStream.close();
                        } catch (IOException e) {
                            e.printStackTrace();
                        }
                    }
                }
            }).start();
            return;
        }
        MediaScannerConnection mediaScannerConnection = this.mMediaScannerConnection;
        if (mediaScannerConnection != null && !mediaScannerConnection.isConnected()) {
            this.mMediaScannerConnection.connect();
            return;
        }
        MediaScannerConnection mediaScannerConnection2 = new MediaScannerConnection(this.mContext, this);
        this.mMediaScannerConnection = mediaScannerConnection2;
        mediaScannerConnection2.connect();
    }

    public static String getMimeType(File file) {
        return URLConnection.getFileNameMap().getContentTypeFor(file.getName());
    }

    @Override // android.media.MediaScannerConnection.MediaScannerConnectionClient
    public void onMediaScannerConnected() {
        if (TextUtils.isEmpty(this.mFilePath)) {
            return;
        }
        scanFile(this.mFilePath);
    }

    @Override // android.media.MediaScannerConnection.OnScanCompletedListener
    public void onScanCompleted(String str, Uri uri) {
        MediaScannerConnection mediaScannerConnection = this.mMediaScannerConnection;
        if (mediaScannerConnection != null) {
            mediaScannerConnection.disconnect();
        }
    }

    public void release() {
        MediaScannerConnection mediaScannerConnection = this.mMediaScannerConnection;
        if (mediaScannerConnection != null) {
            if (mediaScannerConnection.isConnected()) {
                this.mMediaScannerConnection.disconnect();
            }
            this.mMediaScannerConnection = null;
        }
        if (!TextUtils.isEmpty(this.mFilePath)) {
            this.mFilePath = null;
        }
        if (this.mContext != null) {
            this.mContext = null;
        }
    }
}
