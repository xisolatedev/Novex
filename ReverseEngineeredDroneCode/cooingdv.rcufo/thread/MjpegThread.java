package com.cooingdv.rcufo.thread;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.graphics.Paint;
import com.amazon.device.ads.DtbConstants;
import com.cooingdv.rcufo.base.MainApplication;
import com.cooingdv.rcufo.interfaces.OnMjpegListener;
import com.cooingdv.rcufo.models.VideoModel;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.BitmapUtil;
import com.cooingdv.rcufo.utils.Dbug;
import com.cooingdv.rcufo.utils.WifiIdUtils;
import com.mbridge.msdk.playercommon.exoplayer2.extractor.p200ts.PsExtractor;
import java.io.File;
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import org.objectweb.asm.Opcodes;

/* JADX INFO: loaded from: classes2.dex */
public class MjpegThread extends Thread {
    private static final String tag = "MjpegThread";
    private int[] argb;
    private int fakeHeight;
    private int fakeWidth;
    private int fps;
    private int jHeight;
    private int jWidth;
    private Context mContext;
    private OnMjpegListener mOnMjpegListener;
    private Timer timer;
    private VideoModel videoModel;
    private byte[] yuv42sp;
    private int fakeResolution = 0;
    private boolean isVideoThreadRunning = false;
    private final LinkedBlockingQueue<byte[]> mBufList = new LinkedBlockingQueue<>(5);
    private volatile boolean isWaiting = false;
    private boolean isTurnBitmap = false;
    private final ExecutorService cachedThreadPool = Executors.newCachedThreadPool();
    private int encodeTime = 1;
    private int encodeEnd = 1;
    private boolean isPortrait = false;
    private boolean isSavePicture = false;
    private boolean isSetRotate = false;
    private boolean isRotate = false;
    private int focusScale = 0;
    private float focusMoveX = 0.0f;
    private float focusMoveY = 0.0f;
    private float scaleRotate = 1.0f;
    private String photoPath = "";

    public MjpegThread(Context context) {
        this.mContext = context;
    }

    public void setOnMjpegListener(OnMjpegListener onMjpegListener) {
        this.mOnMjpegListener = onMjpegListener;
    }

    public void drawBitmap(byte[] bArr) {
        addData(bArr);
    }

    public void setFakeResolution(int i) {
        this.fakeResolution = i;
    }

    public int getContrastCompressWidth() {
        return this.jWidth;
    }

    public int getContrastCompressHeight() {
        return this.jHeight;
    }

    public void setInitTurnBitmap(boolean z) {
        this.isTurnBitmap = z;
    }

    public void setTurnBitmap(boolean z) {
        this.isTurnBitmap = z;
    }

    public void setModel(VideoModel videoModel) {
        this.videoModel = videoModel;
    }

    public void setFps(int i) {
        this.fps = i;
    }

    public void setFocusScale(int i) {
        this.focusScale = i;
        if (i <= 1) {
            this.focusMoveX = 0.0f;
            this.focusMoveY = 0.0f;
        }
    }

    public void setFocusMove(float f, float f2) {
        if (this.focusScale <= 1) {
            return;
        }
        this.focusMoveX = f;
        this.focusMoveY = f2;
    }

    public boolean getTurnBitmap() {
        return this.isTurnBitmap;
    }

    public void savePicture(String str) {
        this.photoPath = str;
        this.isSavePicture = true;
    }

    public void setRotate() {
        this.isSetRotate = true;
    }

    public void setPortrait(boolean z) {
        this.isPortrait = z;
    }

    public boolean isPortrait() {
        return this.isPortrait;
    }

    void addData(byte[] bArr) {
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

    void openTimer() {
        if (this.timer != null || this.fps == 0) {
            return;
        }
        Dbug.m13285e("fps=", "" + this.fps);
        Timer timer = new Timer();
        this.timer = timer;
        timer.schedule(new TimerTask() { // from class: com.cooingdv.rcufo.thread.MjpegThread.1
            @Override // java.util.TimerTask, java.lang.Runnable
            public void run() {
                if (MjpegThread.this.yuv42sp == null || MjpegThread.this.yuv42sp.length == 0) {
                    return;
                }
                MjpegThread.this.videoModel.offerEncoder(MjpegThread.this.yuv42sp);
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

    /* JADX WARN: Type inference failed for: r2v0 */
    /* JADX WARN: Type inference failed for: r2v1, types: [boolean] */
    /* JADX WARN: Type inference failed for: r2v43 */
    /* JADX WARN: Type inference failed for: r2v5 */
    @Override // java.lang.Thread, java.lang.Runnable
    public void run() {
        boolean z;
        boolean z2;
        Bitmap bitmapCreateBitmap;
        boolean z3;
        Bitmap bitmapCreateBitmap2;
        float f;
        Bitmap bitmapCreateBitmap3;
        float f2;
        float f3;
        float f4;
        float f5;
        float f6;
        float f7;
        Bitmap bitmapCreateBitmap4;
        float f8;
        super.run();
        ?? r2 = 1;
        this.isVideoThreadRunning = true;
        synchronized (this.mBufList) {
            while (this.isVideoThreadRunning) {
                if (this.mBufList.isEmpty()) {
                    try {
                        this.isWaiting = r2;
                        this.mBufList.wait();
                    } catch (InterruptedException e) {
                        e.printStackTrace();
                    }
                } else {
                    this.isWaiting = false;
                    byte[] bArrRemove = this.mBufList.remove();
                    Bitmap bitmapDecodeByteArray = BitmapFactory.decodeByteArray(bArrRemove, 0, bArrRemove.length);
                    if (this.focusScale > r2) {
                        int width = bitmapDecodeByteArray.getWidth();
                        int height = bitmapDecodeByteArray.getHeight();
                        float f9 = this.focusScale / 100.0f;
                        int i = (int) ((width / 2) * f9);
                        int i2 = (int) ((height / 2) * f9);
                        int i3 = ((width / 2) - i) * 2;
                        int i4 = ((height / 2) - i2) * 2;
                        int i5 = (int) (i - (this.focusMoveX / f9));
                        int i6 = (int) (i2 + (this.focusMoveY / f9));
                        if (i5 <= 0) {
                            i5 = 0;
                        }
                        int i7 = width - i3;
                        if (i5 >= i7) {
                            i5 = i7;
                        }
                        if (i6 <= 0) {
                            i6 = 0;
                        }
                        int i8 = height - i4;
                        if (i6 >= i8) {
                            i6 = i8;
                        }
                        bitmapDecodeByteArray = Bitmap.createBitmap(bitmapDecodeByteArray, i5, i6, i3, i4);
                        z = r2 == true ? 1 : 0;
                    } else {
                        z = false;
                    }
                    if (this.isTurnBitmap) {
                        bitmapDecodeByteArray = AppUtils.rotateBitmap(Opcodes.GETFIELD, bitmapDecodeByteArray);
                    }
                    if (bitmapDecodeByteArray != null) {
                        this.jWidth = bitmapDecodeByteArray.getWidth();
                        int height2 = bitmapDecodeByteArray.getHeight();
                        this.jHeight = height2;
                        int i9 = this.jWidth;
                        if (i9 == 800 && height2 == 600) {
                            bitmapDecodeByteArray = Bitmap.createBitmap(bitmapDecodeByteArray, 0, 30, i9, height2 - 60);
                            this.jHeight = 540;
                        } else if (((i9 == 240 && height2 == 320) || ((i9 == 120 && height2 == 160) || (i9 == 160 && height2 == 272))) && !WifiIdUtils.isNoRotate(MainApplication.getInstance().getFakeResolutionNumber())) {
                            bitmapDecodeByteArray = AppUtils.rotateBitmap(90, bitmapDecodeByteArray);
                            int i10 = this.jWidth;
                            if (i10 == 240) {
                                this.jWidth = 320;
                                this.jHeight = PsExtractor.VIDEO_STREAM_MASK;
                            } else if (i10 == 160) {
                                this.jWidth = 272;
                                this.jHeight = Opcodes.IF_ICMPNE;
                            } else if (i10 == 120) {
                                this.jWidth = Opcodes.IF_ICMPNE;
                                this.jHeight = 120;
                            }
                        }
                        if (this.isPortrait) {
                            int i11 = this.jHeight;
                            int i12 = (int) (((i11 * 1.0f) / 16.0f) * 9.0f);
                            bitmapDecodeByteArray = Bitmap.createBitmap(bitmapDecodeByteArray, (this.jWidth - i12) / 2, 0, i12, i11);
                        }
                        Bitmap bitmap = bitmapDecodeByteArray;
                        Dbug.m13286i(tag, "Bitmap size : width :" + bitmap.getWidth() + "height :" + bitmap.getHeight());
                        if (this.isSetRotate) {
                            if (this.isRotate) {
                                this.scaleRotate = (float) (((double) this.scaleRotate) + 0.025d);
                            } else {
                                this.scaleRotate = (float) (((double) this.scaleRotate) - 0.025d);
                            }
                            int width2 = bitmap.getWidth();
                            int height3 = bitmap.getHeight();
                            Matrix matrix = new Matrix();
                            float f10 = this.scaleRotate;
                            if (f10 >= 0.11d) {
                                matrix.postRotate((1.0f - f10) * 360.0f);
                            }
                            float f11 = this.scaleRotate;
                            matrix.postScale(f11, f11);
                            Bitmap bitmapCreateBitmap5 = Bitmap.createBitmap(bitmap, 0, 0, bitmap.getWidth(), bitmap.getHeight(), matrix, true);
                            Bitmap bitmapCreateBitmap6 = Bitmap.createBitmap(width2, height3, Bitmap.Config.ARGB_8888);
                            new Canvas(bitmapCreateBitmap6).drawBitmap(bitmapCreateBitmap5, (width2 / 2) - (bitmapCreateBitmap5.getWidth() / 2), (height3 / 2) - (bitmapCreateBitmap5.getHeight() / 2), (Paint) null);
                            if (!this.isRotate && this.scaleRotate <= 0.1d) {
                                this.isRotate = r2;
                            }
                            if (this.isRotate && this.scaleRotate >= 0.9d) {
                                this.scaleRotate = 1.0f;
                                this.isRotate = false;
                                this.isSetRotate = false;
                            }
                            bitmapCreateBitmap = bitmapCreateBitmap6;
                        } else {
                            bitmapCreateBitmap = bitmap;
                        }
                        VideoModel videoModel = this.videoModel;
                        if (videoModel != null && videoModel.isRecording()) {
                            if (z && this.fakeResolution == 0) {
                                int width3 = bitmapCreateBitmap.getWidth();
                                int height4 = bitmapCreateBitmap.getHeight();
                                Matrix matrix2 = new Matrix();
                                matrix2.postScale(this.jWidth / width3, this.jHeight / height4);
                                bitmapCreateBitmap = Bitmap.createBitmap(bitmapCreateBitmap, 0, 0, width3, height4, matrix2, true);
                            }
                            if (this.fakeResolution != 0) {
                                int width4 = bitmapCreateBitmap.getWidth();
                                int height5 = bitmapCreateBitmap.getHeight();
                                Matrix matrix3 = new Matrix();
                                int i13 = this.fakeResolution;
                                if (i13 != r2) {
                                    if (i13 != 3) {
                                        if (i13 == 4) {
                                            if (height5 > width4) {
                                                if (width4 == 480) {
                                                    int i14 = width4 - 120;
                                                    bitmapCreateBitmap3 = Bitmap.createBitmap(bitmapCreateBitmap, 60, 0, i14, height5);
                                                    f4 = 1080.0f / i14;
                                                } else {
                                                    f4 = 1080.0f / width4;
                                                    bitmapCreateBitmap3 = null;
                                                }
                                                f = 1920.0f / height5;
                                                this.fakeWidth = 1080;
                                                this.fakeHeight = 1920;
                                            } else {
                                                if (height5 == 480) {
                                                    int i15 = height5 - 120;
                                                    bitmapCreateBitmap3 = Bitmap.createBitmap(bitmapCreateBitmap, 0, 60, width4, i15);
                                                    f5 = 1920.0f / width4;
                                                    f = 1080.0f / i15;
                                                } else {
                                                    f5 = 1920.0f / width4;
                                                    f = 1080.0f / height5;
                                                    bitmapCreateBitmap3 = null;
                                                }
                                                f4 = f5;
                                                this.fakeWidth = 1920;
                                                this.fakeHeight = 1080;
                                            }
                                            f2 = f4;
                                        } else if (i13 == 5 || i13 == 6) {
                                            if (height5 > width4) {
                                                if (width4 == 480) {
                                                    int i16 = width4 - 120;
                                                    bitmapCreateBitmap4 = Bitmap.createBitmap(bitmapCreateBitmap, 60, 0, i16, height5);
                                                    f8 = 1080.0f / i16;
                                                } else {
                                                    f8 = 1080.0f / width4;
                                                    bitmapCreateBitmap4 = null;
                                                }
                                                f = 2048.0f / height5;
                                                this.fakeWidth = 1080;
                                                this.fakeHeight = 2048;
                                            } else {
                                                if (height5 == 480) {
                                                    int i17 = height5 - 120;
                                                    bitmapCreateBitmap4 = Bitmap.createBitmap(bitmapCreateBitmap, 0, 60, width4, i17);
                                                    f6 = 2048.0f / width4;
                                                    f7 = 1080.0f / i17;
                                                } else {
                                                    f6 = 2048.0f / width4;
                                                    f7 = 1080.0f / height5;
                                                    bitmapCreateBitmap4 = null;
                                                }
                                                float f12 = f7;
                                                f8 = f6;
                                                f = f12;
                                                this.fakeWidth = 2048;
                                                this.fakeHeight = 1080;
                                            }
                                            f2 = f8;
                                            bitmapCreateBitmap3 = bitmapCreateBitmap4;
                                        } else {
                                            this.fakeWidth = width4;
                                            this.fakeHeight = height5;
                                            f2 = 0.0f;
                                            f = 0.0f;
                                            bitmapCreateBitmap3 = null;
                                        }
                                    } else if (width4 == 1280) {
                                        f2 = 0.0f;
                                        f = 0.0f;
                                        bitmapCreateBitmap3 = null;
                                    } else if (height5 > width4) {
                                        if (width4 == 480) {
                                            int i18 = width4 - 120;
                                            bitmapCreateBitmap3 = Bitmap.createBitmap(bitmapCreateBitmap, 60, 0, i18, height5);
                                            f4 = 720.0f / i18;
                                        } else {
                                            f4 = 720.0f / width4;
                                            bitmapCreateBitmap3 = null;
                                        }
                                        f = 1280.0f / height5;
                                        this.fakeWidth = 720;
                                        this.fakeHeight = 1280;
                                        f2 = f4;
                                    } else {
                                        if (height5 == 480) {
                                            int i19 = height5 - 120;
                                            bitmapCreateBitmap3 = Bitmap.createBitmap(bitmapCreateBitmap, 0, 60, width4, i19);
                                            f3 = 1280.0f / width4;
                                            f = 720.0f / i19;
                                        } else {
                                            f3 = 1280.0f / width4;
                                            f = 720.0f / height5;
                                            bitmapCreateBitmap3 = null;
                                        }
                                        this.fakeWidth = 1280;
                                        this.fakeHeight = 720;
                                        f2 = f3;
                                    }
                                } else if (height5 == 480) {
                                    f2 = 0.0f;
                                    f = 0.0f;
                                    bitmapCreateBitmap3 = null;
                                } else if (height5 > width4) {
                                    f2 = 480.0f / width4;
                                    int i20 = height5 - 160;
                                    f = 640.0f / i20;
                                    this.fakeWidth = DtbConstants.DEFAULT_PLAYER_HEIGHT;
                                    this.fakeHeight = 640;
                                    bitmapCreateBitmap3 = Bitmap.createBitmap(bitmapCreateBitmap, 0, 80, width4, i20);
                                } else {
                                    int i21 = width4 - 160;
                                    f = 480.0f / height5;
                                    this.fakeWidth = 640;
                                    this.fakeHeight = DtbConstants.DEFAULT_PLAYER_HEIGHT;
                                    bitmapCreateBitmap3 = Bitmap.createBitmap(bitmapCreateBitmap, 80, 0, i21, height5);
                                    f2 = 640.0f / i21;
                                }
                                if (f2 == 0.0f || f == 0.0f) {
                                    bitmapCreateBitmap2 = bitmapCreateBitmap3;
                                } else {
                                    matrix3.postScale(f2, f);
                                    if (this.fakeResolution == 1 && bitmapCreateBitmap3 != null) {
                                        bitmapCreateBitmap2 = Bitmap.createBitmap(bitmapCreateBitmap3, 0, 0, bitmapCreateBitmap3.getWidth(), height5, matrix3, true);
                                    } else if (height5 == 480 && bitmapCreateBitmap3 != null) {
                                        bitmapCreateBitmap2 = Bitmap.createBitmap(bitmapCreateBitmap3, 0, 0, bitmapCreateBitmap3.getWidth(), bitmapCreateBitmap3.getHeight(), matrix3, true);
                                    } else {
                                        bitmapCreateBitmap = Bitmap.createBitmap(bitmapCreateBitmap, 0, 0, width4, height5, matrix3, true);
                                        bitmapCreateBitmap2 = bitmapCreateBitmap3;
                                    }
                                }
                            } else {
                                bitmapCreateBitmap2 = null;
                            }
                            if ((this.fakeResolution == 1 && bitmapCreateBitmap2 != null) || bitmapCreateBitmap2 != null) {
                                this.argb = this.videoModel.bitmap2argb(bitmapCreateBitmap2);
                                bitmapCreateBitmap2.recycle();
                            } else {
                                this.argb = this.videoModel.bitmap2argb(bitmapCreateBitmap);
                            }
                            this.cachedThreadPool.execute(new Runnable() { // from class: com.cooingdv.rcufo.thread.MjpegThread$$ExternalSyntheticLambda0
                                @Override // java.lang.Runnable
                                public final void run() {
                                    this.f$0.m35399lambda$run$0$comcooingdvrcufothreadMjpegThread();
                                }
                            });
                            openTimer();
                        } else {
                            cancelTimer();
                        }
                        if (this.isSavePicture) {
                            this.isSavePicture = false;
                            int i22 = this.fakeResolution;
                            z3 = true;
                            if (i22 == 1) {
                                if (bitmapCreateBitmap.getHeight() != 480) {
                                    bitmapCreateBitmap = Bitmap.createBitmap(bitmapCreateBitmap, 80, 0, bitmapCreateBitmap.getWidth() - Opcodes.IF_ICMPNE, bitmapCreateBitmap.getHeight());
                                }
                            } else if ((i22 == 3 || i22 == 4 || i22 == 5 || i22 == 6) && bitmapCreateBitmap.getHeight() == 480) {
                                bitmapCreateBitmap = Bitmap.createBitmap(bitmapCreateBitmap, 0, 60, bitmapCreateBitmap.getWidth(), bitmapCreateBitmap.getHeight() - 120);
                            }
                            BitmapUtil.saveBitmap(this.photoPath, BitmapUtil.fakeBitmap(bitmapCreateBitmap, this.fakeResolution, false));
                            AppUtils.mediaScanImage(this.mContext, new File(this.photoPath));
                        } else {
                            z3 = true;
                        }
                        OnMjpegListener onMjpegListener = this.mOnMjpegListener;
                        z2 = z3;
                        if (onMjpegListener != null) {
                            onMjpegListener.onFrame(bitmapCreateBitmap);
                            z2 = z3;
                        }
                    } else {
                        z2 = r2 == true ? 1 : 0;
                        Dbug.m13285e(tag, "bitmap is null. data size=" + bArrRemove.length);
                    }
                    r2 = z2;
                }
            }
            Dbug.m13285e("stopRunning", "----->");
        }
    }

    /* JADX INFO: renamed from: lambda$run$0$com-cooingdv-rcufo-thread-MjpegThread, reason: not valid java name */
    /* synthetic */ void m35399lambda$run$0$comcooingdvrcufothreadMjpegThread() {
        int i = this.encodeTime + 1;
        this.encodeTime = i;
        int i2 = this.fakeWidth;
        int i3 = this.fakeHeight;
        byte[] bArr = new byte[((i2 * i3) * 3) / 2];
        byte[] bArr2 = new byte[((i2 * i3) * 3) / 2];
        this.videoModel.encodeYUV420SP(bArr, bArr2, this.argb, i2, i3);
        int i4 = this.encodeEnd + 1;
        this.encodeEnd = i4;
        if (i4 <= i) {
            if (this.videoModel.isYUV420P()) {
                this.yuv42sp = bArr2;
                return;
            } else {
                this.yuv42sp = bArr;
                return;
            }
        }
        Dbug.m13285e(tag + "Wrong", "start:" + this.encodeTime + "end:" + this.encodeEnd);
    }

    public void release() {
        stopRunning();
    }
}
