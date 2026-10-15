package com.cooingdv.rcufo.thread;

import com.cooingdv.rcufo.utils.StorageUtil;
import java.util.Timer;
import java.util.TimerTask;

/* JADX INFO: loaded from: classes2.dex */
public class FreeSpaceMonitor {
    private static final long DEFAULT_PERIOD = 1000;
    private static final long DEFAULT_THRESHOLD = 10485760;
    private static final long MIN_PERIOD = 500;
    private static final long MIN_THRESHOLD = 10485760;
    private FreeSpaceCheckerListener mListener;
    private long mPeriod;
    private long mThreshold;
    private Timer mTimer;

    public interface FreeSpaceCheckerListener {
        void onExceed();
    }

    public FreeSpaceMonitor() {
        this.mThreshold = 10485760L;
        this.mPeriod = 1000L;
    }

    public FreeSpaceMonitor(long j, long j2) {
        this.mThreshold = j;
        this.mPeriod = j2;
    }

    public void start() {
        stop();
        FreeSpaceCheckerTimerTask freeSpaceCheckerTimerTask = new FreeSpaceCheckerTimerTask();
        Timer timer = new Timer();
        this.mTimer = timer;
        timer.schedule(freeSpaceCheckerTimerTask, 0L, this.mPeriod);
    }

    public void stop() {
        Timer timer = this.mTimer;
        if (timer != null) {
            timer.cancel();
            this.mTimer = null;
        }
    }

    public boolean checkFreeSpace() {
        return StorageUtil.getFreeDiskSpace() > this.mThreshold;
    }

    private class FreeSpaceCheckerTimerTask extends TimerTask {
        private FreeSpaceCheckerTimerTask() {
        }

        @Override // java.util.TimerTask, java.lang.Runnable
        public void run() {
            if (FreeSpaceMonitor.this.checkFreeSpace() || FreeSpaceMonitor.this.mListener == null) {
                return;
            }
            FreeSpaceMonitor.this.mListener.onExceed();
        }
    }

    public long getThreshold() {
        return this.mThreshold;
    }

    public void setThreshold(long j) {
        if (j < 10485760) {
            this.mThreshold = 10485760L;
        } else {
            this.mThreshold = j;
        }
    }

    public long getPeriod() {
        return this.mPeriod;
    }

    public void setPeriod(long j) {
        if (j < MIN_PERIOD) {
            this.mPeriod = MIN_PERIOD;
        } else {
            this.mPeriod = j;
        }
    }

    public void setListener(FreeSpaceCheckerListener freeSpaceCheckerListener) {
        this.mListener = freeSpaceCheckerListener;
    }
}
