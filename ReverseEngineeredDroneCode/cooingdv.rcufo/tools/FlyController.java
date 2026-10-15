package com.cooingdv.rcufo.tools;

import android.os.Handler;
import android.widget.ImageView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.interfaces.FlyControllerDelegate;
import com.cooingdv.rcufo.socket.SocketClient;
import com.cooingdv.rcufo.utils.Dbug;
import com.google.common.base.Ascii;
import java.lang.ref.WeakReference;
import java.util.Timer;
import java.util.TimerTask;

/* JADX INFO: loaded from: classes2.dex */
public class FlyController {
    private FlyControllerDelegate mDelegate;
    private Timer mFlyControlTimer;
    private WeakReference<Handler> mHandlerRef;
    private String TAG = getClass().getSimpleName();
    private final int SEND_COMMAND_INTERVAL = 50;
    private final int RESET_COMMAND_INTERVAL = 1000;
    public final int CONTROL_VALUES_MAX = 255;
    public final int CONTROL_VALUES_DEFAULT = 128;
    public final int CONTROL_VALUES_MIN = 1;
    private final int COMMAND_LENGTH = 8;
    private final int CONTROL_VALUES_BYTE0 = 102;
    private final int CONTROL_VALUES_BYTE7 = 153;
    private int controlByte1 = 128;
    private int controlByte2 = 128;
    private int controlAccelerator = 128;
    private int controlTurn = 128;
    private boolean isControlMode = false;
    private boolean isFixedHeightMode = false;
    private boolean isGravitySensor = false;
    private boolean isGestureMode = false;
    private boolean isTrackMode = false;
    private boolean isFastFly = false;
    private boolean isFastDrop = false;
    private boolean isEmergencyStop = false;
    private boolean isCircleTurn = false;
    private boolean isCircleTurnEnd = false;
    private boolean isNoHeadMode = false;
    private boolean isGyroCorrection = false;
    private boolean isUnLock = false;
    private boolean isFastReturn = false;
    private boolean isMusicMode = false;
    private boolean isFilterMode = false;

    public FlyController(Handler handler) {
        this.mHandlerRef = new WeakReference<>(handler);
    }

    public void setController(boolean z) {
        this.isControlMode = z;
        if (z) {
            if (this.mFlyControlTimer == null) {
                Timer timer = new Timer();
                this.mFlyControlTimer = timer;
                timer.schedule(new FlyControlTask(), 50L, 50L);
                return;
            }
            return;
        }
        Timer timer2 = this.mFlyControlTimer;
        if (timer2 != null) {
            timer2.cancel();
            this.mFlyControlTimer = null;
            SocketClient.getInstance().debugSend(new byte[]{8, 1});
        }
    }

    private class FlyControlTask extends TimerTask {
        private FlyControlTask() {
        }

        /* JADX WARN: Multi-variable type inference failed */
        /* JADX WARN: Type inference failed for: r1v1, types: [boolean, int] */
        /* JADX WARN: Type inference failed for: r1v17 */
        /* JADX WARN: Type inference failed for: r1v18 */
        /* JADX WARN: Type inference failed for: r1v19 */
        /* JADX WARN: Type inference failed for: r1v2, types: [int] */
        /* JADX WARN: Type inference failed for: r1v20 */
        /* JADX WARN: Type inference failed for: r1v21 */
        /* JADX WARN: Type inference failed for: r1v22 */
        /* JADX WARN: Type inference failed for: r1v23 */
        /* JADX WARN: Type inference failed for: r1v24 */
        /* JADX WARN: Type inference failed for: r1v25 */
        /* JADX WARN: Type inference failed for: r1v26 */
        /* JADX WARN: Type inference failed for: r1v27 */
        /* JADX WARN: Type inference failed for: r1v28 */
        /* JADX WARN: Type inference failed for: r1v3, types: [int] */
        /* JADX WARN: Type inference failed for: r1v4, types: [int] */
        /* JADX WARN: Type inference failed for: r1v5, types: [int] */
        /* JADX WARN: Type inference failed for: r1v7, types: [int] */
        /* JADX WARN: Type inference failed for: r1v8, types: [int] */
        /* JADX WARN: Type inference failed for: r4v2, types: [java.lang.StringBuilder] */
        /* JADX WARN: Type inference failed for: r7v10, types: [int] */
        /* JADX WARN: Type inference failed for: r7v17 */
        /* JADX WARN: Type inference failed for: r7v18 */
        /* JADX WARN: Type inference failed for: r7v9, types: [boolean, int] */
        @Override // java.util.TimerTask, java.lang.Runnable
        public void run() {
            ?? r1;
            ?? r2 = FlyController.this.isFastFly;
            ?? r3 = r2;
            if (FlyController.this.isFastDrop) {
                r3 = r2 + 2;
            }
            ?? r4 = r3;
            if (FlyController.this.isEmergencyStop) {
                r4 = r3 + 4;
            }
            ?? r5 = r4;
            if (FlyController.this.isCircleTurnEnd) {
                r5 = r4 + 8;
            }
            ?? r6 = r5;
            if (FlyController.this.isNoHeadMode) {
                r6 = r5 + 16;
            }
            if (FlyController.this.isFastReturn || FlyController.this.isUnLock) {
                r1 = r6;
                r1 = r6 + 32;
            }
            r1 = r6;
            ?? r7 = r1;
            if (FlyController.this.isGyroCorrection) {
                r7 = r1 + 128;
            }
            if (FlyController.this.controlTurn > 255) {
                FlyController.this.controlTurn = 255;
            } else if (FlyController.this.controlTurn < 1) {
                FlyController.this.controlTurn = 1;
            }
            if (FlyController.this.controlAccelerator == 1) {
                FlyController.this.controlAccelerator = 0;
            }
            if (FlyController.this.controlByte1 > 255) {
                FlyController.this.controlByte1 = 255;
            } else if (FlyController.this.controlByte1 < 1) {
                FlyController.this.controlByte1 = 1;
            }
            if (FlyController.this.controlByte2 > 255) {
                FlyController.this.controlByte2 = 255;
            } else if (FlyController.this.controlByte2 < 1) {
                FlyController.this.controlByte2 = 1;
            }
            int i = (((FlyController.this.controlByte1 ^ FlyController.this.controlByte2) ^ FlyController.this.controlAccelerator) ^ FlyController.this.controlTurn) ^ (r7 & 255);
            if (SocketClient.getInstance().getDeviceType() != 10) {
                int i2 = (FlyController.this.isFastFly || FlyController.this.isFastDrop) ? 1 : 0;
                if (FlyController.this.isEmergencyStop) {
                    i2 += 2;
                }
                if (FlyController.this.isGyroCorrection) {
                    i2 += 4;
                }
                if (FlyController.this.isCircleTurnEnd) {
                    i2 += 8;
                }
                if (FlyController.this.isGestureMode) {
                    i2 += 64;
                }
                ?? r8 = FlyController.this.isNoHeadMode;
                ?? r9 = r8;
                if (FlyController.this.isFixedHeightMode) {
                    r9 = r8 + 2;
                }
                byte[] bArr = {102, Ascii.DC4, (byte) FlyController.this.controlByte1, (byte) FlyController.this.controlByte2, (byte) FlyController.this.controlAccelerator, (byte) FlyController.this.controlTurn, (byte) i2, (byte) r9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (byte) ((i2 ^ (((FlyController.this.controlByte2 ^ FlyController.this.controlByte1) ^ FlyController.this.controlAccelerator) ^ FlyController.this.controlTurn)) ^ (r9 & 255)), -103};
                byte[] bArr2 = new byte[21];
                bArr2[0] = 3;
                System.arraycopy(bArr, 0, bArr2, 1, 20);
                SocketClient.getInstance().debugSend(bArr2);
            } else {
                byte[] bArr3 = {102, (byte) FlyController.this.controlByte1, (byte) FlyController.this.controlByte2, (byte) FlyController.this.controlAccelerator, (byte) FlyController.this.controlTurn, (byte) r7, (byte) i, -103};
                byte[] bArr4 = new byte[9];
                bArr4[0] = 3;
                System.arraycopy(bArr3, 0, bArr4, 1, 8);
                SocketClient.getInstance().debugSend(bArr4);
            }
            Dbug.m13286i(FlyController.this.TAG, "byte0:102,byte1:" + FlyController.this.controlByte1 + ",byte2:" + FlyController.this.controlByte2 + ",byte3:" + FlyController.this.controlAccelerator + ",byte4:" + FlyController.this.controlTurn + ",byte5:" + r7 + ",byte6:" + i + ",byte7:153");
        }
    }

    public void setDelegate(FlyControllerDelegate flyControllerDelegate) {
        this.mDelegate = flyControllerDelegate;
    }

    public boolean isControlMode() {
        return this.isControlMode;
    }

    public int getControlByte1() {
        return this.controlByte1;
    }

    public boolean isFixedHeightMode() {
        return this.isFixedHeightMode;
    }

    public void setFixedHeightMode(boolean z) {
        this.isFixedHeightMode = z;
    }

    public boolean isGravitySensor() {
        return this.isGravitySensor;
    }

    public void setGravitySensor(boolean z) {
        this.isGravitySensor = z;
    }

    public boolean isGestureMode() {
        return this.isGestureMode;
    }

    public void setGestureMode(boolean z) {
        this.isGestureMode = z;
    }

    public boolean isTrackMode() {
        return this.isTrackMode;
    }

    public void setTrackMode(boolean z) {
        this.isTrackMode = z;
    }

    public void setControlByte1(int i) {
        this.controlByte1 = i;
    }

    public int getControlByte2() {
        return this.controlByte2;
    }

    public void setControlByte2(int i) {
        this.controlByte2 = i;
    }

    public int getControlAccelerator() {
        return this.controlAccelerator;
    }

    public void setControlAccelerator(int i) {
        this.controlAccelerator = i;
    }

    public int getControlTurn() {
        return this.controlTurn;
    }

    public void setControlTurn(int i) {
        this.controlTurn = i;
    }

    public boolean isFastFly() {
        return this.isFastFly;
    }

    public void setFastFly(final ImageView imageView) {
        if (this.isFastFly) {
            return;
        }
        this.isFastFly = true;
        imageView.setImageResource(C3033R.mipmap.icon_up_yellow);
        WeakReference<Handler> weakReference = this.mHandlerRef;
        if (weakReference == null || weakReference.get() == null) {
            return;
        }
        this.mHandlerRef.get().postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.tools.FlyController.1
            @Override // java.lang.Runnable
            public void run() {
                FlyController.this.isFastFly = false;
                imageView.setImageResource(C3033R.drawable.drawable_up);
            }
        }, 1000L);
    }

    public boolean isFastDrop() {
        return this.isFastDrop;
    }

    public void setFastDrop(final ImageView imageView) {
        if (this.isFastDrop) {
            return;
        }
        this.isFastDrop = true;
        imageView.setImageResource(C3033R.mipmap.icon_down_yellow);
        WeakReference<Handler> weakReference = this.mHandlerRef;
        if (weakReference == null || weakReference.get() == null) {
            return;
        }
        this.mHandlerRef.get().postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.tools.FlyController.2
            @Override // java.lang.Runnable
            public void run() {
                FlyController.this.isFastDrop = false;
                imageView.setImageResource(C3033R.drawable.drawable_down);
            }
        }, 1000L);
    }

    public boolean isEmergencyStop() {
        return this.isEmergencyStop;
    }

    public void setEmergencyStop(final ImageView imageView) {
        if (this.isEmergencyStop) {
            return;
        }
        this.isEmergencyStop = true;
        imageView.setImageResource(C3033R.mipmap.icon_stop_yellow);
        WeakReference<Handler> weakReference = this.mHandlerRef;
        if (weakReference == null || weakReference.get() == null) {
            return;
        }
        this.mHandlerRef.get().postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.tools.FlyController.3
            @Override // java.lang.Runnable
            public void run() {
                FlyController.this.isEmergencyStop = false;
                imageView.setImageResource(C3033R.drawable.drawable_stop);
            }
        }, 1000L);
    }

    public boolean isCircleTurn() {
        return this.isCircleTurn;
    }

    public void setCircleTurn(ImageView imageView) {
        boolean z = !this.isCircleTurn;
        this.isCircleTurn = z;
        if (z) {
            imageView.setImageResource(C3033R.drawable.drawable_top_fip_yellow);
        } else {
            imageView.setImageResource(C3033R.drawable.drawable_top_fip);
        }
    }

    public boolean isCircleTurnEnd() {
        return this.isCircleTurnEnd;
    }

    public void setCircleTurnEnd() {
        if (this.isCircleTurnEnd) {
            return;
        }
        this.isCircleTurn = false;
        this.isCircleTurnEnd = true;
        WeakReference<Handler> weakReference = this.mHandlerRef;
        if (weakReference == null || weakReference.get() == null) {
            return;
        }
        this.mHandlerRef.get().postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.tools.FlyController.4
            @Override // java.lang.Runnable
            public void run() {
                FlyController.this.isCircleTurnEnd = false;
                FlyController.this.controlByte1 = 128;
                FlyController.this.controlByte2 = 128;
            }
        }, 600L);
    }

    public boolean isNoHeadMode() {
        return this.isNoHeadMode;
    }

    public void setNoHeadMode(ImageView imageView) {
        boolean z = !this.isNoHeadMode;
        this.isNoHeadMode = z;
        if (z) {
            imageView.setImageResource(C3033R.drawable.drawable_head_mode_yellow);
        } else {
            imageView.setImageResource(C3033R.drawable.drawable_head_mode_icon);
        }
    }

    public boolean isGyroCorrection() {
        return this.isGyroCorrection;
    }

    public void setGyroCorrection(final ImageView imageView) {
        if (this.isGyroCorrection) {
            return;
        }
        this.isGyroCorrection = true;
        imageView.setImageResource(C3033R.mipmap.icon_gyro_ywllow);
        WeakReference<Handler> weakReference = this.mHandlerRef;
        if (weakReference == null || weakReference.get() == null) {
            return;
        }
        this.mHandlerRef.get().postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.tools.FlyController.5
            @Override // java.lang.Runnable
            public void run() {
                FlyController.this.isGyroCorrection = false;
                imageView.setImageResource(C3033R.drawable.drawable_gyr_icon);
            }
        }, 2000L);
    }

    public boolean isMusicMode() {
        return this.isMusicMode;
    }

    public void setMusicMode(boolean z) {
        this.isMusicMode = z;
    }

    public boolean isFilterMode() {
        return this.isFilterMode;
    }

    public void setFilterMode(boolean z) {
        this.isFilterMode = z;
    }
}
