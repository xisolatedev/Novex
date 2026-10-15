package com.cooingdv.rcufo.base;

import android.app.ActivityManager;
import android.app.Application;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Process;
import android.text.TextUtils;
import android.widget.Toast;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.Dbug;
import com.unad.sdk.UNAD;
import com.unad.sdk.dto.AdError;

/* JADX INFO: loaded from: classes2.dex */
public class MainApplication extends Application implements IConstants {
    private static final String TAG = "MainApplication";
    private static MainApplication sInstance;
    private String WifiSSID;
    private int appVersion;
    private String deviceUUID;
    private Toast mToastLong;
    private String appName = null;
    private int fakeResolutionNumber = 0;
    private boolean isBrowsing = false;
    private boolean isDoubleCamera = false;
    private boolean isGoogle = true;
    private boolean isFirstStartAPP = true;
    public boolean isRun = false;

    public void setRun(boolean z) {
        this.isRun = z;
    }

    @Override // android.app.Application
    public void onCreate() {
        super.onCreate();
        sInstance = this;
        this.appName = PreferencesHelper.getSharedPreferences(getApplicationContext()).getString(IConstants.KEY_ROOT_PATH_NAME, null);
        PackageManager packageManager = getPackageManager();
        if (TextUtils.isEmpty(this.appName)) {
            this.appName = getApplicationInfo().loadLabel(packageManager).toString();
        }
        try {
            this.appVersion = packageManager.getPackageInfo(getPackageName(), 0).versionCode;
        } catch (PackageManager.NameNotFoundException e) {
            e.printStackTrace();
        }
        Dbug.openOrCloseDebug(false);
        boolean z = PreferencesHelper.getSharedPreferences(this).getBoolean(IConstants.FIRST_START_APP, true);
        this.isFirstStartAPP = z;
        if (z) {
            PreferencesHelper.putBooleanValue(this, IConstants.FIRST_START_APP, false);
            this.isFirstStartAPP = false;
            return;
        }
        String processName = getProcessName(this);
        if (processName == null || !processName.equalsIgnoreCase(getPackageName())) {
            return;
        }
        UNAD.initialize("Adgo-app-1817844034", getApplicationContext(), new UNAD.InitCallback() { // from class: com.cooingdv.rcufo.base.MainApplication.1
            @Override // com.unad.sdk.UNAD.InitCallback
            public void onSuccess() {
                Dbug.m13286i(MainApplication.TAG, "onSuccess");
            }

            @Override // com.unad.sdk.UNAD.InitCallback
            public void onError(AdError adError) {
                Dbug.m13286i(MainApplication.TAG, "error:" + adError.getMessage());
            }
        });
    }

    private String getProcessName(Context context) {
        if (context == null) {
            return null;
        }
        for (ActivityManager.RunningAppProcessInfo runningAppProcessInfo : ((ActivityManager) context.getSystemService("activity")).getRunningAppProcesses()) {
            if (runningAppProcessInfo.pid == Process.myPid()) {
                return runningAppProcessInfo.processName;
            }
        }
        return null;
    }

    public static MainApplication getInstance() {
        return sInstance;
    }

    @Override // android.app.Application, android.content.ComponentCallbacks
    public void onLowMemory() {
        super.onLowMemory();
    }

    public String getAppName() {
        return this.appName;
    }

    public boolean isFirstStartAPP() {
        return this.isFirstStartAPP;
    }

    public void setFirstStartAPP(boolean z) {
        this.isFirstStartAPP = z;
    }

    public int getAppVersion() {
        return this.appVersion;
    }

    public boolean isGoogle() {
        return this.isGoogle;
    }

    public boolean isDoubleCamera() {
        return this.isDoubleCamera;
    }

    public void setDoubleCamera(boolean z) {
        this.isDoubleCamera = z;
    }

    public int getFakeResolutionNumber() {
        return this.fakeResolutionNumber;
    }

    public void setFakeResolutionNumber(int i) {
        this.fakeResolutionNumber = i;
    }

    public String getDeviceUUID() {
        return this.deviceUUID;
    }

    public void setDeviceUUID(String str) {
        this.deviceUUID = str;
    }

    public String getWifiSSID() {
        return this.WifiSSID;
    }

    public void setWifiSSID(String str) {
        this.WifiSSID = str;
    }

    public void setIsBrowsing(boolean z) {
        this.isBrowsing = z;
    }

    public boolean getIsBrowsing() {
        return this.isBrowsing;
    }

    public void showToastLong(String str) {
        Toast toast = this.mToastLong;
        if (toast != null) {
            toast.setText(str);
        } else {
            Toast toastMakeText = Toast.makeText(this, str, 1);
            this.mToastLong = toastMakeText;
            toastMakeText.setGravity(17, 0, 0);
        }
        this.mToastLong.show();
    }
}
