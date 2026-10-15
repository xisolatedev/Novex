package com.cooingdv.rcufo.tools;

import android.app.Activity;
import android.view.OrientationEventListener;
import com.cooingdv.rcufo.utils.Dbug;
import java.lang.ref.WeakReference;

/* JADX INFO: loaded from: classes2.dex */
public class ScreenSensorHelper {
    private static final String TAG = "ScreenSensorHelper";
    private WeakReference<Activity> mActivityWeakRef;
    private OrientationEventListener mLandOrientationListener;
    private OrientationEventListener mPortOrientationListener;
    private boolean isPortLock = false;
    private boolean isLandLock = false;

    public ScreenSensorHelper(Activity activity) {
        this.mActivityWeakRef = new WeakReference<>(activity);
        int i = 3;
        this.mLandOrientationListener = new OrientationEventListener(activity, i) { // from class: com.cooingdv.rcufo.tools.ScreenSensorHelper.1
            @Override // android.view.OrientationEventListener
            public void onOrientationChanged(int i2) {
                Activity activity2;
                Dbug.m13284d(ScreenSensorHelper.TAG, "mLandOrientationListener");
                if (((i2 >= 100 || i2 <= 80) && (i2 >= 280 || i2 <= 260)) || ScreenSensorHelper.this.isLandLock || (activity2 = (Activity) ScreenSensorHelper.this.mActivityWeakRef.get()) == null) {
                    return;
                }
                Dbug.m13285e(ScreenSensorHelper.TAG, "转到了横屏");
                activity2.setRequestedOrientation(0);
                ScreenSensorHelper.this.isLandLock = true;
                ScreenSensorHelper.this.isPortLock = false;
            }
        };
        this.mPortOrientationListener = new OrientationEventListener(activity, i) { // from class: com.cooingdv.rcufo.tools.ScreenSensorHelper.2
            @Override // android.view.OrientationEventListener
            public void onOrientationChanged(int i2) {
                Activity activity2;
                Dbug.m13288w(ScreenSensorHelper.TAG, "mPortOrientationListener");
                if ((i2 <= 350 && (i2 >= 190 || i2 <= 170)) || ScreenSensorHelper.this.isPortLock || (activity2 = (Activity) ScreenSensorHelper.this.mActivityWeakRef.get()) == null) {
                    return;
                }
                Dbug.m13285e(ScreenSensorHelper.TAG, "转到了竖屏");
                activity2.setRequestedOrientation(1);
                ScreenSensorHelper.this.isPortLock = true;
                ScreenSensorHelper.this.isLandLock = false;
            }
        };
    }

    public void disable() {
        Dbug.m13285e(TAG, "disable");
        this.mPortOrientationListener.disable();
        this.mLandOrientationListener.disable();
        this.isPortLock = false;
        this.isLandLock = false;
    }

    public void enable() {
        this.mPortOrientationListener.enable();
        this.mLandOrientationListener.enable();
    }

    public void setPortLock(boolean z) {
        this.isPortLock = z;
    }

    public void setLandLock(boolean z) {
        this.isLandLock = z;
    }
}
