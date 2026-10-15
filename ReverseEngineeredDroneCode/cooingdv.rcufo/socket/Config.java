package com.cooingdv.rcufo.socket;

/* JADX INFO: loaded from: classes2.dex */
public final class Config {
    public static final int BOTTOM_VIEW_HEIGHT_LANDSCAPE = 32;
    public static final int BOTTOM_VIEW_HEIGHT_PORTRAIT = 49;
    public static final String FTP_HOST = "192.168.1.1";
    public static final String FTP_PASSWORD = "ftp";
    public static final String FTP_ROOT_DIR = "/0/";
    public static final String FTP_USERNAME = "ftp";
    public static final String IMAGE_PATH = "PHOTO";
    public static final String LOCAL_IMAGE_SUFFIX = ".jpg";
    public static final String LOCAL_VIDEO_SUFFIX = ".avi";
    public static final int NAVIGATION_BAR_HEIGHT_LANDSCAPE = 32;
    public static final int NAVIGATION_BAR_HEIGHT_PORTRAIT = 44;
    public static final String PREFS_NAME = "Prefs";
    public static final String PREVIEW_ADDRESS = "rtsp://192.168.1.1:7070/webcam";
    public static final int RECONNECTION_INTERVAL = 500;
    public static final String REMOTE_IMAGE_SUFFIX = ".jpg";
    public static final String REMOTE_VIDEO_SUFFIX = ".avi";
    public static final int SEND_COMMAND_INTERVAL = 40;
    public static final String SERVER_IP = "192.168.1.1";
    public static final int SERVER_PORT = 7070;
    public static final int TCP_ALIVE_INTERVAL = 5000;
    public static final int TCP_RECONNECTION_INTERVAL = 1;
    public static final String TCP_SERVER_HOST = "192.168.1.1";
    public static final int TCP_SERVER_PORT = 5000;
    public static final boolean USE_INTERNAL_PHOTO_VIEWER = true;
    public static final boolean USE_INTERNAL_VIDEO_PLAYER = true;
    public static final String VIDEO_PATH = "DCIM";

    public static String VIDEO_THUMB_PATH(String str) {
        return "http://192.168.1.1/DCIM/" + str;
    }

    public static String VIDEO_LIVE_PATH(String str) {
        return "rtsp://192.168.1.1:7070/file/DCIM/" + str;
    }

    public static String PHOTO_THUMB_PATH(String str) {
        return "http://192.168.1.1/PHOTO/T/" + str;
    }

    public static String PHOTO_HTTP_PATH(String str) {
        return "http://192.168.1.1/PHOTO/O/" + str;
    }
}
