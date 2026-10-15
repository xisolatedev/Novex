package com.cooingdv.rcufo.thread;

import android.os.Handler;
import android.os.SystemClock;
import java.lang.ref.WeakReference;

/* JADX INFO: loaded from: classes2.dex */
public class MyTimer extends Thread {
    private static final int MSG_UPDATE_RECORDING_UI = 43971;
    private WeakReference<Handler> handlerRef;
    private boolean isTimerRunning = false;
    private int timer = 0;

    public boolean isTimerRunning() {
        return this.isTimerRunning;
    }

    public MyTimer(Handler handler) {
        this.handlerRef = null;
        this.handlerRef = new WeakReference<>(handler);
    }

    public void setTimer(int i) {
        this.timer = i;
    }

    public void stopTimer() {
        this.timer = -1;
        this.isTimerRunning = false;
        interrupt();
    }

    @Override // java.lang.Thread, java.lang.Runnable
    public void run() {
        this.isTimerRunning = true;
        while (this.isTimerRunning) {
            SystemClock.sleep(1000L);
            this.timer++;
            WeakReference<Handler> weakReference = this.handlerRef;
            if (weakReference != null && weakReference.get() != null) {
                this.handlerRef.get().obtainMessage(MSG_UPDATE_RECORDING_UI, Integer.valueOf(this.timer)).sendToTarget();
            }
        }
    }
}
