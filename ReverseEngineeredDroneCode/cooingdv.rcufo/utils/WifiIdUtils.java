package com.cooingdv.rcufo.utils;

import com.cooingdv.rcufo.tools.IConstants;

/* JADX INFO: loaded from: classes2.dex */
public class WifiIdUtils implements IConstants {
    private static final int CHANGE_PASSWORD_8K = 80;
    private static final int CHANGE_PASSWORD_DOUBLE_8K = 81;
    private static final int CHANGE_PASSWORD_FLOW_480 = 85;
    private static final int CHANGE_PASSWORD_FLOW_720 = 88;
    private static final int CHANGE_PASSWORD_FLOW_8K = 82;
    private static final int DOUBLE_RESOLUTION_1080 = 43;
    private static final int DOUBLE_RESOLUTION_4K = 44;
    private static final int DOUBLE_RESOLUTION_720 = 41;
    private static final int DOUBLE_RESOLUTION_8K = 45;
    private static final int FLOW_RESOLUTION_1080 = 91;
    private static final int FLOW_RESOLUTION_4K = 92;
    private static final int FLOW_RESOLUTION_4K_NO_ROTATE = 94;
    private static final int FLOW_RESOLUTION_720 = 90;
    private static final int FLOW_RESOLUTION_8K = 93;
    private static final int FLOW_RESOLUTION_8K_NO_ROTATE = 99;
    private static final int FLOW_RESOLUTION_8K_ORIENTATION_CAMERA = 101;
    private static final int FLOW_RESOLUTION_8K_ORIENTATION_CAMERA_1080 = 103;
    private static final int FLOW_RESOLUTION_8K_ORIENTATION_CAMERA_1080_SCREEN = 105;
    private static final int FLOW_RESOLUTION_8K_THREE_CAMERA = 100;
    private static final int HAIQU_KL41_8K = 86;
    private static final int HAIQU_KL42_8K = 87;
    private static final int KY_DOUBLE_RESOLUTION_1080 = 23;
    private static final int KY_DOUBLE_RESOLUTION_4K = 24;
    private static final int KY_DOUBLE_RESOLUTION_720 = 21;
    private static final int KY_DOUBLE_RESOLUTION_8K = 51;
    private static final int KY_RESOLUTION_1080 = 12;
    private static final int KY_RESOLUTION_480 = 5;
    private static final int KY_RESOLUTION_4k = 19;
    private static final int KY_RESOLUTION_720 = 9;
    private static final int KY_RESOLUTION_8k = 20;
    private static final int KY_SPI_RESOLUTION_1080 = 65;
    private static final int KY_SPI_RESOLUTION_480 = 63;
    private static final int KY_SPI_RESOLUTION_4K = 66;
    private static final int KY_SPI_RESOLUTION_720 = 64;
    private static final int KY_SPI_RESOLUTION_8K = 67;
    private static final int RESOLUTION_1080 = 29;
    private static final int RESOLUTION_480 = 26;
    private static final int RESOLUTION_4k = 30;
    private static final int RESOLUTION_720 = 27;
    private static final int RESOLUTION_8k = 31;
    private static final int SPI_KL41_8K = 84;
    private static final int SPI_KL42_8K = 83;
    private static final int SPI_RESOLUTION_1080 = 70;
    private static final int SPI_RESOLUTION_480 = 68;
    private static final int SPI_RESOLUTION_4K = 71;
    private static final int SPI_RESOLUTION_720 = 69;
    private static final int SPI_RESOLUTION_8K = 72;

    public static boolean isFakeResolution1080(int i) {
        return i == 12 || i == 23 || i == 65 || i == 91 || i == 29 || i == 43 || i == 70;
    }

    public static boolean isFakeResolution480(int i) {
        return i == 5 || i == 63 || i == 85 || i == 26 || i == 68;
    }

    public static boolean isFakeResolution4K(int i) {
        return i == 92 || i == 94 || i == 30 || i == 44 || i == 71;
    }

    public static boolean isFakeResolution640720(int i) {
        return false;
    }

    public static boolean isFakeResolution720(int i) {
        return i == 9 || i == 21 || i == 64 || i == 90 || i == 27 || i == 41 || i == 69 || i == 88;
    }

    public static boolean isFakeResolution8K(int i) {
        return i == 20 || i == 51 || i == 67 || i == 19 || i == 24 || i == 66 || i == 80 || i == 93 || i == 99 || i == 100 || i == 101 || i == 103 || i == 81 || i == 82 || i == 83 || i == 84 || i == 31 || i == 45 || i == 72 || i == 105 || i == 87 || i == 86;
    }

    public static boolean isGL(int i) {
        return (i >= 90 && i <= 101) || i == 103 || i == 82 || i == 85 || i == 88;
    }

    public static boolean isNoRotate(int i) {
        return i == 94 || i == 99;
    }

    public static boolean isPasswordWifi(int i) {
        return i == 80 || i == 81 || i == 82 || i == 85 || i == 88;
    }

    public static int getFakeResolution(int i) {
        if (isFakeResolution480(i)) {
            return 1;
        }
        if (isFakeResolution640720(i)) {
            return 2;
        }
        if (isFakeResolution720(i)) {
            return 3;
        }
        if (isFakeResolution1080(i)) {
            return 4;
        }
        if (isFakeResolution4K(i)) {
            return 5;
        }
        return isFakeResolution8K(i) ? 6 : 0;
    }

    public static boolean isSupport(int i) {
        return isFakeResolution480(i) || isFakeResolution720(i) || isFakeResolution1080(i) || isFakeResolution4K(i) || isFakeResolution8K(i);
    }
}
