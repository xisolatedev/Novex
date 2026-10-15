package com.cooingdv.rcufo.libs;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import android.media.AudioTrack;
import android.os.Process;
import android.util.AttributeSet;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import com.amazon.device.ads.DtbConstants;
import com.cooingdv.rcufo.models.VideoModel;
import com.cooingdv.rcufo.tools.ScanFilesHelper;
import com.cooingdv.rcufo.utils.Dbug;
import java.lang.ref.WeakReference;
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;

/* JADX INFO: loaded from: classes2.dex */
public class MjpegView extends SurfaceView implements SurfaceHolder.Callback {
    private static BitmapFactory.Options bitmapOptions = null;
    private static final String tag = "MjpegView";
    private int fakeResolutionType;
    private boolean initIsTurnBitmap;
    private AudioThread mAudioThread;
    private int mJpegHeight;
    private int mJpegWidth;
    private VideoThread mVideoThread;
    private boolean surfaceDone;

    static /* synthetic */ String access$100() {
        return tag;
    }

    static /* synthetic */ BitmapFactory.Options access$700() {
        return bitmapOptions;
    }

    public MjpegView(Context context) {
        super(context);
        this.surfaceDone = false;
        this.mJpegWidth = 640;
        this.mJpegHeight = DtbConstants.DEFAULT_PLAYER_HEIGHT;
        this.initIsTurnBitmap = false;
        this.fakeResolutionType = 0;
        init();
    }

    public MjpegView(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
        this.surfaceDone = false;
        this.mJpegWidth = 640;
        this.mJpegHeight = DtbConstants.DEFAULT_PLAYER_HEIGHT;
        this.initIsTurnBitmap = false;
        this.fakeResolutionType = 0;
        init();
    }

    private void init() {
        Dbug.m13286i(tag, "init.........................");
        getHolder().addCallback(this);
        setFocusable(true);
        BitmapFactory.Options options = new BitmapFactory.Options();
        bitmapOptions = options;
        options.inPreferredConfig = Bitmap.Config.ARGB_8888;
        bitmapOptions.inPurgeable = true;
    }

    public void setSetResolution(boolean z) {
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setSetResolution(z);
        }
    }

    public void drawBitmap(byte[] bArr) {
        VideoThread videoThread;
        if (!this.surfaceDone || (videoThread = this.mVideoThread) == null || bArr == null) {
            return;
        }
        videoThread.addData(bArr);
    }

    public void setFakeResolution(int i) {
        this.fakeResolutionType = i;
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setFakeResolution(i);
        }
    }

    public int getContrastCompressWidth() {
        int i = this.mJpegWidth;
        VideoThread videoThread = this.mVideoThread;
        return videoThread != null ? videoThread.getjWidth() : i;
    }

    public int getContrastCompressHeight() {
        int i = this.mJpegHeight;
        VideoThread videoThread = this.mVideoThread;
        return videoThread != null ? videoThread.getjHeight() : i;
    }

    public void setInitTurnBitmap(boolean z) {
        this.initIsTurnBitmap = z;
    }

    public void setTurnBitmap(boolean z) {
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setTurnBitmap(z);
        }
    }

    public void setModel(VideoModel videoModel) {
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setModel(videoModel);
        }
    }

    public void setFps(int i) {
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setFps(i);
        }
    }

    public void setFocusScale(int i) {
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setFocusScale(i);
        }
    }

    public void setFocusMove(float f, float f2) {
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setFocusMoveX(f);
            this.mVideoThread.setFocusMoveY(f2);
        }
    }

    public boolean getTurnBitmap() {
        VideoThread videoThread = this.mVideoThread;
        return videoThread != null && videoThread.isTurnBitmap;
    }

    public void savePicture(String str, ScanFilesHelper scanFilesHelper) {
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.savePicture(str, scanFilesHelper);
        }
    }

    private class VideoThread extends Thread {
        private int[] argb;
        private int dispHeight;
        private int dispWidth;
        private int fakeResolution;
        private int fps;
        private int jHeight;
        private int jWidth;
        private WeakReference<SurfaceHolder> mWeakRefSurfaceHolder;
        private ScanFilesHelper scanFilesHelper;
        private Timer timer;
        private VideoModel videoModel;
        private byte[] yuv42sp;
        private boolean isVideoThreadRunning = false;
        private final LinkedBlockingQueue<byte[]> mBufList = new LinkedBlockingQueue<>(5);
        private volatile boolean isWaiting = false;
        private boolean isDropFrame = true;
        private boolean isOptimize = false;
        private boolean isTurnBitmap = false;
        private ExecutorService cachedThreadPool = Executors.newCachedThreadPool();
        private int encodeTime = 1;
        private int encodeEnd = 1;
        private int focusScale = 0;
        private float focusMoveX = 0.0f;
        private float focusMoveY = 0.0f;
        private boolean isSetResolution = false;
        private boolean isSavePicture = false;
        private String photoPath = "";

        static /* synthetic */ int access$1208(VideoThread videoThread) {
            int i = videoThread.encodeEnd;
            videoThread.encodeEnd = i + 1;
            return i;
        }

        static /* synthetic */ int access$808(VideoThread videoThread) {
            int i = videoThread.encodeTime;
            videoThread.encodeTime = i + 1;
            return i;
        }

        VideoThread(SurfaceHolder surfaceHolder, int i, int i2, boolean z) {
            Dbug.m13285e(MjpegView.tag, "==== VideoThread onCreate ====jpegWidth : " + i + " ,jpegHeight = " + i2);
            this.jWidth = i;
            this.jHeight = i2;
            this.mWeakRefSurfaceHolder = new WeakReference<>(surfaceHolder);
            setTurnBitmap(z);
            this.fakeResolution = MjpegView.this.fakeResolutionType;
        }

        void savePicture(String str, ScanFilesHelper scanFilesHelper) {
            this.photoPath = str;
            this.scanFilesHelper = scanFilesHelper;
            this.isSavePicture = true;
        }

        void setFocusScale(int i) {
            this.focusScale = i;
            if (i <= 1) {
                this.focusMoveX = 0.0f;
                this.focusMoveY = 0.0f;
            }
        }

        void setFocusMoveX(float f) {
            if (this.focusScale <= 1) {
                return;
            }
            this.focusMoveX = f;
        }

        void setFocusMoveY(float f) {
            if (this.focusScale <= 1) {
                return;
            }
            this.focusMoveY = f;
        }

        void setFakeResolution(int i) {
            this.fakeResolution = i;
        }

        void setSetResolution(boolean z) {
            this.isSetResolution = z;
        }

        int getjWidth() {
            return this.jWidth;
        }

        int getjHeight() {
            return this.jHeight;
        }

        void setTurnBitmap(boolean z) {
            this.isTurnBitmap = z;
        }

        void addData(byte[] bArr) {
            this.isOptimize = true;
            if (this.mBufList.remainingCapacity() <= 1) {
                this.mBufList.poll();
            }
            try {
                this.mBufList.put(bArr);
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
            if (this.isWaiting) {
                synchronized (this.mBufList) {
                    this.mBufList.notify();
                }
            }
        }

        void stopRunning() {
            this.isVideoThreadRunning = false;
            synchronized (this.mBufList) {
                this.mBufList.notify();
                this.mBufList.clear();
            }
        }

        void setSurfaceSize(int i, int i2) {
            this.dispWidth = i;
            this.dispHeight = i2;
        }

        void setModel(VideoModel videoModel) {
            this.videoModel = videoModel;
        }

        void setFps(int i) {
            this.fps = i;
        }

        void openTimer() {
            if (this.timer != null || this.fps == 0) {
                return;
            }
            Dbug.m13285e("fps=", "" + this.fps);
            Timer timer = new Timer();
            this.timer = timer;
            timer.schedule(new TimerTask() { // from class: com.cooingdv.rcufo.libs.MjpegView.VideoThread.1
                @Override // java.util.TimerTask, java.lang.Runnable
                public void run() {
                    if ((!VideoThread.this.isWaiting || !VideoThread.this.isDropFrame) && VideoThread.this.yuv42sp != null && VideoThread.this.yuv42sp.length != 0) {
                        VideoThread.this.videoModel.offerEncoder(VideoThread.this.yuv42sp);
                        if (VideoThread.this.isWaiting) {
                            VideoThread.this.isDropFrame = true;
                            return;
                        }
                        return;
                    }
                    VideoThread.this.isDropFrame = false;
                }
            }, 100L, 1000 / this.fps);
        }

        void cancelTimer() {
            Timer timer = this.timer;
            if (timer != null) {
                timer.cancel();
                this.timer = null;
            }
        }

        private Rect resizeRect(int i, int i2) {
            return new Rect(0, 0, this.dispWidth, this.dispHeight);
        }

        /* JADX WARN: Failed to calculate best type for var: r5v11 ??
        jadx.core.utils.exceptions.JadxRuntimeException: Type update failed for variable: r5v11 ??, new type: int
        	at jadx.core.dex.visitors.typeinference.TypeUpdate.apply(TypeUpdate.java:109)
        	at jadx.core.dex.visitors.typeinference.TypeUpdate.apply(TypeUpdate.java:59)
        	at jadx.core.dex.visitors.typeinference.TypeInferenceVisitor.calculateFromBounds(TypeInferenceVisitor.java:147)
        	at jadx.core.dex.visitors.typeinference.TypeInferenceVisitor.setBestType(TypeInferenceVisitor.java:125)
        	at jadx.core.dex.visitors.typeinference.TypeInferenceVisitor.lambda$runTypePropagation$2(TypeInferenceVisitor.java:103)
        	at java.base/java.util.ArrayList.forEach(ArrayList.java:1604)
        	at jadx.core.dex.visitors.typeinference.TypeInferenceVisitor.runTypePropagation(TypeInferenceVisitor.java:103)
        	at jadx.core.dex.visitors.typeinference.TypeInferenceVisitor.visit(TypeInferenceVisitor.java:75)
        Caused by: java.lang.NullPointerException
         */
        /*  JADX ERROR: Types fix failed
            jadx.core.utils.exceptions.JadxRuntimeException: Type update failed for variable: r6v3 ??, new type: char
            	at jadx.core.dex.visitors.typeinference.TypeUpdate.apply(TypeUpdate.java:109)
            	at jadx.core.dex.visitors.typeinference.TypeUpdate.apply(TypeUpdate.java:59)
            	at jadx.core.dex.visitors.typeinference.FixTypesVisitor.tryPossibleTypes(FixTypesVisitor.java:186)
            	at jadx.core.dex.visitors.typeinference.FixTypesVisitor.deduceType(FixTypesVisitor.java:245)
            	at jadx.core.dex.visitors.typeinference.FixTypesVisitor.tryDeduceTypes(FixTypesVisitor.java:224)
            	at jadx.core.dex.visitors.typeinference.FixTypesVisitor.visit(FixTypesVisitor.java:94)
            Caused by: java.lang.NullPointerException
            */
        @Override // java.lang.Thread, java.lang.Runnable
        public void run() {
            /*
                Method dump skipped, instruction units count: 811
                To view this dump change 'Code comments level' option to 'DEBUG'
            */
            throw new UnsupportedOperationException("Method not decompiled: com.cooingdv.rcufo.libs.MjpegView.VideoThread.run():void");
        }
    }

    private static class AudioThread extends Thread {
        private AudioTrack mAudioTrack;
        private final LinkedBlockingQueue<byte[]> mQueue = new LinkedBlockingQueue<>(3);
        private boolean isRunning = false;

        AudioThread() {
            Process.setThreadPriority(-16);
            if (this.mAudioTrack == null) {
                AudioTrack audioTrack = new AudioTrack(3, 8000, 4, 2, AudioTrack.getMinBufferSize(8000, 4, 2), 1);
                this.mAudioTrack = audioTrack;
                if (audioTrack.getPlayState() != 3) {
                    this.mAudioTrack.play();
                }
            }
        }

        void stopRunning() {
            this.isRunning = false;
            if (this.mAudioTrack != null) {
                Dbug.m13286i(MjpegView.tag, "stopRunning: getState=" + this.mAudioTrack.getState() + ", getPlayState=" + this.mAudioTrack.getPlayState());
            }
            AudioTrack audioTrack = this.mAudioTrack;
            if (audioTrack == null || audioTrack.getState() != 1) {
                return;
            }
            this.mAudioTrack.stop();
            this.mAudioTrack.release();
            Dbug.m13286i(MjpegView.tag, "stopRunning: release----getState=" + this.mAudioTrack.getState() + ", getPlayState=" + this.mAudioTrack.getPlayState());
            this.mAudioTrack = null;
        }

        @Override // java.lang.Thread, java.lang.Runnable
        public void run() throws InterruptedException {
            super.run();
            this.isRunning = true;
            while (this.isRunning) {
                byte[] bArrTake = new byte[0];
                try {
                    bArrTake = this.mQueue.take();
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
                AudioTrack audioTrack = this.mAudioTrack;
                if (audioTrack != null && audioTrack.getState() == 1 && this.mAudioTrack.getPlayState() == 3) {
                    this.mAudioTrack.write(bArrTake, 0, bArrTake.length);
                }
            }
        }
    }

    public void release() {
        this.mJpegWidth = 640;
        this.mJpegHeight = DtbConstants.DEFAULT_PLAYER_HEIGHT;
        AudioThread audioThread = this.mAudioThread;
        if (audioThread != null) {
            audioThread.stopRunning();
            this.mAudioThread = null;
        }
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.stopRunning();
            this.mVideoThread = null;
        }
        if (getHolder() == null || getHolder().getSurface() == null) {
            return;
        }
        getHolder().getSurface().release();
    }

    @Override // android.view.SurfaceHolder.Callback
    public void surfaceCreated(SurfaceHolder surfaceHolder) {
        this.surfaceDone = true;
        Dbug.m13285e(tag, "surfaceCreated-----------------------mJpegWidth=" + this.mJpegWidth + " ,mJpegHeight = " + this.mJpegHeight);
        if (this.mVideoThread == null) {
            this.mVideoThread = new VideoThread(surfaceHolder, this.mJpegWidth, this.mJpegHeight, this.initIsTurnBitmap);
        }
        if (this.mVideoThread.getState() == Thread.State.NEW) {
            this.mVideoThread.start();
        }
        if (this.mAudioThread == null) {
            this.mAudioThread = new AudioThread();
        }
        if (this.mAudioThread.getState() == Thread.State.NEW) {
            this.mAudioThread.start();
        }
    }

    @Override // android.view.SurfaceHolder.Callback
    public void surfaceChanged(SurfaceHolder surfaceHolder, int i, int i2, int i3) {
        Dbug.m13286i(tag, "surfaceChanged--------------w=" + i2 + ", h=" + i3 + ", width=" + getWidth() + ", height=" + getHeight() + ", surfaceDone=" + this.surfaceDone);
        VideoThread videoThread = this.mVideoThread;
        if (videoThread != null) {
            videoThread.setSurfaceSize(i2, i3);
        }
    }

    @Override // android.view.SurfaceHolder.Callback
    public void surfaceDestroyed(SurfaceHolder surfaceHolder) {
        Dbug.m13288w(tag, "surfaceDestroyed------------------------surfaceDone=" + this.surfaceDone);
        this.surfaceDone = false;
        release();
    }
}
