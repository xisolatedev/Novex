package com.cooingdv.rcufo.socket;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.MainApplication;
import com.cooingdv.rcufo.dialog.EnterPasswordDialog;
import com.cooingdv.rcufo.dialog.PasswordDialog;
import com.cooingdv.rcufo.interfaces.OnSocketListener;
import com.cooingdv.rcufo.tools.BufChangeHex;
import com.cooingdv.rcufo.tools.IActions;
import com.cooingdv.rcufo.tools.TimeRecordManager;
import com.cooingdv.rcufo.utils.Dbug;
import com.cooingdv.rcufo.utils.WifiIdUtils;
import java.util.Timer;
import java.util.TimerTask;
import java.util.concurrent.locks.ReentrantLock;
import tv.danmaku.ijk.media.widget.IjkMpOptions;
import tv.danmaku.ijk.media.widget.IjkVideoView;

/* JADX INFO: loaded from: classes2.dex */
public class SocketClient {

    /* JADX INFO: renamed from: GL */
    public static final int f10183GL = 2;
    private static final int RECONNECT_INTERVAL = 500;
    private static String TAG = "SocketClient";

    /* JADX INFO: renamed from: TC */
    public static final int f10184TC = 10;
    private static final int VIDEO_VIEW_ASPECT = 3;
    private static final int VIDEO_VIEW_RENDER = 2;
    private static SocketClient mSocketClient;
    private Activity activity;
    private EnterPasswordDialog enterPasswordDialog;
    private boolean isChangePassword;
    private boolean isPasswordCorrect;
    private boolean isRestart;
    private OnSocketListener mOnSocketListener;
    private IjkVideoView mVideoView;
    private Timer netSendTimer;
    private PasswordDialog passwordDialog;
    private TimeRecordManager timeRecordManager;
    private UdpComm udpComm;
    private String mVideoPath = Config.PREVIEW_ADDRESS;
    private final ReentrantLock sendLock = new ReentrantLock();
    private String wifiPassword = "";
    private int mDeviceType = 0;
    private int switchCameraReset = 0;
    private boolean isSwitchCamera = false;
    private boolean isSwitchingCamera = false;
    private final IjkVideoView.IVideoView.OnPreparedListener mPlayerPreparedListener = new IjkVideoView.IVideoView.OnPreparedListener() { // from class: com.cooingdv.rcufo.socket.SocketClient.1
        @Override // tv.danmaku.ijk.media.widget.IjkVideoView.IVideoView.OnPreparedListener
        public void onPrepared(IjkVideoView ijkVideoView) {
            SocketClient.this.timeRecordManager.addConnectionRecord();
            SocketClient.this.mVideoView.setOutputOriginalVideo(true);
            if (SocketClient.this.isSwitchingCamera) {
                SocketClient.this.isSwitchingCamera = false;
            } else {
                SocketClient.this.startUdpTask();
            }
            if (SocketClient.this.mOnSocketListener != null) {
                SocketClient.this.mOnSocketListener.onConnected();
            }
            MainApplication.getInstance().setFakeResolutionNumber(0);
            if (!SocketClient.this.isRestart) {
                SocketClient.this.isChangePassword = false;
                SocketClient.this.isPasswordCorrect = false;
                SocketClient.this.wifiPassword = "";
            }
            SocketClient.this.isRestart = false;
        }
    };
    private final IjkVideoView.IVideoView.OnErrorListener mPlayerErrorListener = new IjkVideoView.IVideoView.OnErrorListener() { // from class: com.cooingdv.rcufo.socket.SocketClient$$ExternalSyntheticLambda4
        @Override // tv.danmaku.ijk.media.widget.IjkVideoView.IVideoView.OnErrorListener
        public final boolean onError(IjkVideoView ijkVideoView, int i, int i2) {
            return this.f$0.m35396lambda$new$0$comcooingdvrcufosocketSocketClient(ijkVideoView, i, i2);
        }
    };
    private final IjkVideoView.IVideoView.OnReceivedOriginalDataListener mReceivedOriginalDataListener = new IjkVideoView.IVideoView.OnReceivedOriginalDataListener() { // from class: com.cooingdv.rcufo.socket.SocketClient.2
        @Override // tv.danmaku.ijk.media.widget.IjkVideoView.IVideoView.OnReceivedOriginalDataListener
        public void onReceivedOriginalData(IjkVideoView ijkVideoView, byte[] bArr, int i, int i2, int i3, int i4) {
            if (SocketClient.this.mOnSocketListener != null) {
                SocketClient.this.mOnSocketListener.onVideo(bArr);
            }
        }
    };
    private final IjkVideoView.IVideoView.OnCompletionListener mPlayerCompletionListener = new IjkVideoView.IVideoView.OnCompletionListener() { // from class: com.cooingdv.rcufo.socket.SocketClient.3
        @Override // tv.danmaku.ijk.media.widget.IjkVideoView.IVideoView.OnCompletionListener
        public void onCompletion(IjkVideoView ijkVideoView) {
            SocketClient.this.mVideoView.stopPlayback();
            SocketClient.this.mVideoView.release(true);
            SocketClient.this.mVideoView.stopBackgroundPlay();
            SocketClient.this.cancelUdpTask();
        }
    };

    public static SocketClient getInstance() {
        if (mSocketClient == null) {
            synchronized (SocketClient.class) {
                if (mSocketClient == null) {
                    mSocketClient = new SocketClient();
                }
            }
        }
        return mSocketClient;
    }

    public void setOnSocketListener(OnSocketListener onSocketListener) {
        this.mOnSocketListener = onSocketListener;
    }

    public boolean isChangePassword() {
        return this.isChangePassword;
    }

    public int getDeviceType() {
        return this.mDeviceType;
    }

    public boolean isPasswordCorrect() {
        return this.isPasswordCorrect;
    }

    public void setPasswordCorrect(boolean z) {
        this.isPasswordCorrect = z;
    }

    public String getWifiPassword() {
        return this.wifiPassword;
    }

    public boolean initVideoView(IjkVideoView ijkVideoView, Context context) {
        if (ijkVideoView == null) {
            return false;
        }
        this.mVideoView = ijkVideoView;
        this.timeRecordManager = TimeRecordManager.getInstance(context);
        this.mVideoView.setRender(2);
        this.mVideoView.setAspectRatio(3);
        this.mVideoView.setOnPreparedListener(this.mPlayerPreparedListener);
        this.mVideoView.setOnErrorListener(this.mPlayerErrorListener);
        this.mVideoView.setOnReceivedOriginalDataListener(this.mReceivedOriginalDataListener);
        this.mVideoView.setOnCompletionListener(this.mPlayerCompletionListener);
        applyOptionsToVideoView(this.mVideoView);
        this.mVideoView.setVideoPath(Config.PREVIEW_ADDRESS);
        return true;
    }

    private void applyOptionsToVideoView(IjkVideoView ijkVideoView) {
        IjkMpOptions ijkMpOptionsDefaultOptions = IjkMpOptions.defaultOptions();
        ijkMpOptionsDefaultOptions.setPlayerOption("mediacodec", 0L);
        ijkMpOptionsDefaultOptions.setPlayerOption("readtimeout", 5000000L);
        ijkMpOptionsDefaultOptions.setPlayerOption("preferred-image-type", 0L);
        ijkMpOptionsDefaultOptions.setPlayerOption("image-quality-min", 2L);
        ijkMpOptionsDefaultOptions.setPlayerOption("image-quality-max", 20L);
        ijkMpOptionsDefaultOptions.setPlayerOption("preferred-video-type", 2L);
        ijkMpOptionsDefaultOptions.setPlayerOption("video-need-transcoding", 1L);
        ijkMpOptionsDefaultOptions.setPlayerOption("mjpeg-pix-fmt", 1L);
        ijkMpOptionsDefaultOptions.setPlayerOption("video-quality-min", 2L);
        ijkMpOptionsDefaultOptions.setPlayerOption("video-quality-max", 20L);
        ijkMpOptionsDefaultOptions.setPlayerOption("x264-option-preset", 0L);
        ijkMpOptionsDefaultOptions.setPlayerOption("x264-option-tune", 5L);
        ijkMpOptionsDefaultOptions.setPlayerOption("x264-option-profile", 1L);
        ijkMpOptionsDefaultOptions.setPlayerOption("x264-params", "crf=23");
        ijkMpOptionsDefaultOptions.setPlayerOption("auto-drop-record-frame", 3L);
        ijkMpOptionsDefaultOptions.setCodecOption("err_detect", "explode");
        ijkVideoView.setOptions(ijkMpOptionsDefaultOptions);
    }

    /* JADX INFO: renamed from: lambda$new$0$com-cooingdv-rcufo-socket-SocketClient, reason: not valid java name */
    /* synthetic */ boolean m35396lambda$new$0$comcooingdvrcufosocketSocketClient(IjkVideoView ijkVideoView, int i, int i2) {
        stopAndRestartPlayback();
        cancelUdpTask();
        return true;
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void startUdpTask() {
        UdpComm udpComm = UdpComm.getInstance("192.168.1.1", 7099);
        this.udpComm = udpComm;
        udpComm.setCallback(new UdpComm.UdpCommCallback() { // from class: com.cooingdv.rcufo.socket.SocketClient$$ExternalSyntheticLambda2
            @Override // com.cooingdv.rcufo.socket.UdpComm.UdpCommCallback
            public final void onReceiveData(byte[] bArr) {
                this.f$0.m35397lambda$startUdpTask$1$comcooingdvrcufosocketSocketClient(bArr);
            }
        });
        this.udpComm.initSendRecvThread();
        Timer timer = new Timer();
        this.netSendTimer = timer;
        timer.schedule(new HeartBeatTask(), 0L, 1000L);
    }

    /* JADX WARN: Code duplicated, block: B:31:0x007d A[PHI: r3
      0x007d: PHI (r3v20 byte) = (r3v9 byte), (r3v22 byte) binds: [B:33:0x0085, B:30:0x007b] A[DONT_GENERATE, DONT_INLINE]] */
    /* JADX INFO: renamed from: lambda$startUdpTask$1$com-cooingdv-rcufo-socket-SocketClient, reason: not valid java name */
    /* synthetic */ void m35397lambda$startUdpTask$1$comcooingdvrcufosocketSocketClient(byte[] bArr) {
        byte b;
        char cCharAt;
        char cCharAt2;
        char cCharAt3;
        char cCharAt4;
        char cCharAt5;
        char cCharAt6;
        char cCharAt7;
        char cCharAt8;
        OnSocketListener onSocketListener = this.mOnSocketListener;
        if (onSocketListener != null) {
            onSocketListener.onReceiver(bArr);
        }
        Dbug.m13286i(TAG, "DATA = " + BufChangeHex.bytesToHex(bArr));
        if (bArr.length >= 1) {
            boolean z = false;
            byte b2 = bArr[0];
            if (WifiIdUtils.isGL(b2)) {
                if (this.mDeviceType != 2) {
                    this.mDeviceType = 2;
                }
            } else if (this.mDeviceType != 10) {
                this.mDeviceType = 10;
            }
            if (MainApplication.getInstance().getFakeResolutionNumber() == 0) {
                MainApplication.getInstance().setFakeResolutionNumber(b2);
                MainApplication.getInstance().sendBroadcast(new Intent(IActions.ACTION_SET_FAKE_RESOLUTION));
            }
            if (bArr.length >= 2) {
                this.switchCameraReset = bArr[1];
            }
            if (this.activity == null || bArr.length < 15) {
                return;
            }
            if (this.mDeviceType == 2 && bArr.length >= 19) {
                b = bArr[8];
                if (bArr[9] == 1) {
                    z = true;
                }
            } else {
                b = bArr[5];
                if (bArr[6] == 1) {
                    z = true;
                }
            }
            if (b2 == 80 || b2 == 81 || b2 == 82 || b2 == 85 || b2 == 88) {
                if (b == 0 && !z) {
                    if (this.enterPasswordDialog == null) {
                        this.enterPasswordDialog = new EnterPasswordDialog();
                    }
                    this.enterPasswordDialog.setHiddenCancel();
                    if (!this.enterPasswordDialog.isShowing()) {
                        this.activity.runOnUiThread(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient.4
                            @Override // java.lang.Runnable
                            public void run() {
                                SocketClient.this.wifiPassword = "1";
                                SocketClient.this.enterPasswordDialog.show(SocketClient.this.activity.getFragmentManager(), "PASSWORD_DIALOG");
                            }
                        });
                    }
                } else if (b == 1) {
                    this.isChangePassword = true;
                    EnterPasswordDialog enterPasswordDialog = this.enterPasswordDialog;
                    if (enterPasswordDialog != null && enterPasswordDialog.isShowing()) {
                        this.enterPasswordDialog.dismiss();
                        this.activity.runOnUiThread(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient.5
                            @Override // java.lang.Runnable
                            public void run() {
                                if (SocketClient.this.enterPasswordDialog.isHiddenCancel()) {
                                    MainApplication.getInstance().showToastLong(SocketClient.this.activity.getString(C3033R.string.please_restart_device));
                                    SocketClient.this.enterPasswordDialog = null;
                                } else {
                                    MainApplication.getInstance().showToastLong(SocketClient.this.activity.getString(C3033R.string.password_changed_successfully));
                                }
                            }
                        });
                        this.isRestart = true;
                        stopAndRestartPlayback();
                    }
                }
            }
            if (b == 0 && z && this.wifiPassword.equals("")) {
                if (this.mDeviceType == 2 && bArr.length >= 19) {
                    cCharAt = BufChangeHex.byteToHex(bArr[11]).charAt(1);
                    cCharAt4 = BufChangeHex.byteToHex(bArr[12]).charAt(1);
                    cCharAt7 = BufChangeHex.byteToHex(bArr[13]).charAt(1);
                    cCharAt3 = BufChangeHex.byteToHex(bArr[14]).charAt(1);
                    cCharAt5 = BufChangeHex.byteToHex(bArr[15]).charAt(1);
                    cCharAt8 = BufChangeHex.byteToHex(bArr[16]).charAt(1);
                    cCharAt6 = BufChangeHex.byteToHex(bArr[17]).charAt(1);
                    cCharAt2 = BufChangeHex.byteToHex(bArr[18]).charAt(1);
                } else {
                    cCharAt = BufChangeHex.byteToHex(bArr[7]).charAt(1);
                    char cCharAt9 = BufChangeHex.byteToHex(bArr[8]).charAt(1);
                    char cCharAt10 = BufChangeHex.byteToHex(bArr[9]).charAt(1);
                    char cCharAt11 = BufChangeHex.byteToHex(bArr[10]).charAt(1);
                    char cCharAt12 = BufChangeHex.byteToHex(bArr[11]).charAt(1);
                    char cCharAt13 = BufChangeHex.byteToHex(bArr[12]).charAt(1);
                    char cCharAt14 = BufChangeHex.byteToHex(bArr[13]).charAt(1);
                    cCharAt2 = BufChangeHex.byteToHex(bArr[14]).charAt(1);
                    cCharAt3 = cCharAt11;
                    cCharAt4 = cCharAt9;
                    cCharAt5 = cCharAt12;
                    cCharAt6 = cCharAt14;
                    cCharAt7 = cCharAt10;
                    cCharAt8 = cCharAt13;
                }
                StringBuilder sb = new StringBuilder();
                sb.append(cCharAt);
                sb.append(cCharAt4);
                sb.append(cCharAt7);
                sb.append(cCharAt3);
                sb.append(cCharAt5);
                sb.append(cCharAt8);
                sb.append(cCharAt6);
                sb.append(cCharAt2);
                this.wifiPassword = sb.toString();
                if (this.isPasswordCorrect) {
                    return;
                }
                if (this.passwordDialog == null) {
                    this.passwordDialog = new PasswordDialog();
                }
                if (this.passwordDialog.isShowing()) {
                    return;
                }
                this.activity.runOnUiThread(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient.6
                    @Override // java.lang.Runnable
                    public void run() {
                        SocketClient.this.passwordDialog.show(SocketClient.this.activity.getFragmentManager(), "ENTER_PASSWORD_DIALOG");
                    }
                });
            }
        }
    }

    private class HeartBeatTask extends TimerTask {
        private HeartBeatTask() {
        }

        @Override // java.util.TimerTask, java.lang.Runnable
        public void run() {
            SocketClient.this.debugSend(new byte[]{1, 1});
        }
    }

    public void debugSend(byte[] bArr) {
        this.sendLock.lock();
        UdpComm udpComm = this.udpComm;
        if (udpComm != null) {
            udpComm.send(bArr);
        }
        this.sendLock.unlock();
    }

    public void setActivity(Activity activity) {
        this.activity = activity;
    }

    public void changePassword(final Activity activity) {
        if (this.enterPasswordDialog == null) {
            this.enterPasswordDialog = new EnterPasswordDialog();
        }
        this.enterPasswordDialog.setTitle();
        if (this.enterPasswordDialog.isShowing()) {
            return;
        }
        activity.runOnUiThread(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient.7
            @Override // java.lang.Runnable
            public void run() {
                SocketClient.this.enterPasswordDialog.show(activity.getFragmentManager(), "PASSWORD_DIALOG");
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void cancelUdpTask() {
        if (this.isSwitchingCamera) {
            return;
        }
        this.sendLock.lock();
        Timer timer = this.netSendTimer;
        if (timer != null) {
            timer.cancel();
            this.netSendTimer = null;
        }
        UdpComm udpComm = this.udpComm;
        if (udpComm != null) {
            udpComm.setCallback(null);
            this.udpComm.closeClient();
            this.udpComm = null;
        }
        this.sendLock.unlock();
    }

    public boolean isActive() {
        IjkVideoView ijkVideoView = this.mVideoView;
        return ijkVideoView != null && ijkVideoView.isPlaying();
    }

    public void switchCamera() {
        byte[] bArr;
        if (this.isSwitchingCamera) {
            return;
        }
        this.isRestart = true;
        if (this.switchCameraReset == 2) {
            this.mVideoView.post(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient.8
                @Override // java.lang.Runnable
                public void run() {
                    SocketClient.this.mVideoView.stopPlayback();
                    SocketClient.this.mVideoView.release(true);
                    SocketClient.this.mVideoView.stopBackgroundPlay();
                }
            });
        }
        boolean z = !this.isSwitchCamera;
        this.isSwitchCamera = z;
        if (z) {
            bArr = new byte[]{6, 2};
        } else {
            bArr = new byte[]{6, 1};
        }
        debugSend(bArr);
        int i = this.switchCameraReset;
        if (i == 1) {
            this.isSwitchingCamera = true;
            this.mVideoView.post(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient$$ExternalSyntheticLambda3
                @Override // java.lang.Runnable
                public final void run() {
                    this.f$0.m35398lambda$switchCamera$2$comcooingdvrcufosocketSocketClient();
                }
            });
        } else if (i == 2) {
            this.mVideoView.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient.9
                @Override // java.lang.Runnable
                public void run() {
                    SocketClient.this.mVideoView.setRender(2);
                    SocketClient.this.mVideoView.setAspectRatio(3);
                    SocketClient.this.mVideoView.setVideoPath(SocketClient.this.mVideoPath);
                    SocketClient.this.mVideoView.start();
                }
            }, 600L);
            this.isSwitchingCamera = true;
        }
    }

    /* JADX INFO: renamed from: lambda$switchCamera$2$com-cooingdv-rcufo-socket-SocketClient, reason: not valid java name */
    /* synthetic */ void m35398lambda$switchCamera$2$comcooingdvrcufosocketSocketClient() {
        this.mVideoView.setRender(2);
        this.mVideoView.setAspectRatio(3);
        this.mVideoView.setVideoPath(this.mVideoPath);
        this.mVideoView.start();
    }

    public void start() {
        IjkVideoView ijkVideoView = this.mVideoView;
        if (ijkVideoView != null) {
            ijkVideoView.setRender(2);
            this.mVideoView.setAspectRatio(3);
            this.mVideoView.setVideoPath(this.mVideoPath);
            this.mVideoView.start();
        }
    }

    public void stop() {
        IjkVideoView ijkVideoView = this.mVideoView;
        if (ijkVideoView != null) {
            if (!ijkVideoView.isBackgroundPlayEnabled()) {
                this.mVideoView.stopPlayback();
                this.mVideoView.release(true);
                this.mVideoView.stopBackgroundPlay();
                return;
            }
            this.mVideoView.enterBackground();
        }
    }

    private void stopAndRestartPlayback() {
        this.mVideoView.post(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient$$ExternalSyntheticLambda0
            @Override // java.lang.Runnable
            public final void run() {
                this.f$0.m13264x6bee876b();
            }
        });
        this.mVideoView.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.socket.SocketClient$$ExternalSyntheticLambda1
            @Override // java.lang.Runnable
            public final void run() {
                this.f$0.m13265xc30c784a();
            }
        }, 500L);
    }

    /* JADX INFO: renamed from: lambda$stopAndRestartPlayback$3$com-cooingdv-rcufo-socket-SocketClient */
    /* synthetic */ void m13264x6bee876b() {
        this.mVideoView.stopPlayback();
        this.mVideoView.release(true);
        this.mVideoView.stopBackgroundPlay();
    }

    /* JADX INFO: renamed from: lambda$stopAndRestartPlayback$4$com-cooingdv-rcufo-socket-SocketClient */
    /* synthetic */ void m13265xc30c784a() {
        this.mVideoView.setRender(2);
        this.mVideoView.setAspectRatio(3);
        this.mVideoView.setVideoPath(this.mVideoPath);
        this.mVideoView.start();
    }
}
