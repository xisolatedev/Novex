package com.cooingdv.rcufo.fragment;

import android.content.Intent;
import android.content.res.AssetManager;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Point;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Message;
import android.provider.Settings;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewPropertyAnimator;
import android.view.animation.LinearInterpolator;
import android.widget.AdapterView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListAdapter;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import com.amazon.device.ads.DtbConstants;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.activity.BrowseFileActivity;
import com.cooingdv.rcufo.activity.MusicActivity;
import com.cooingdv.rcufo.adapter.TopListViewAdapter;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.base.MainApplication;
import com.cooingdv.rcufo.interfaces.OnMjpegListener;
import com.cooingdv.rcufo.interfaces.OnMusicComposeListener;
import com.cooingdv.rcufo.interfaces.OnSocketListener;
import com.cooingdv.rcufo.libs.HorizontalListView;
import com.cooingdv.rcufo.libs.MyScaleView;
import com.cooingdv.rcufo.libs.RockerView;
import com.cooingdv.rcufo.libs.TrackView;
import com.cooingdv.rcufo.libs.verticalseekbar.VerticalSeekBar;
import com.cooingdv.rcufo.models.GravityModel;
import com.cooingdv.rcufo.models.VideoModel;
import com.cooingdv.rcufo.socket.SocketClient;
import com.cooingdv.rcufo.thread.MjpegThread;
import com.cooingdv.rcufo.thread.MyTimer;
import com.cooingdv.rcufo.tools.BufChangeHex;
import com.cooingdv.rcufo.tools.FlyController;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.tools.ScanFilesHelper;
import com.cooingdv.rcufo.tools.ScreenSensorHelper;
import com.cooingdv.rcufo.tools.TimeFormater;
import com.cooingdv.rcufo.tools.TrackAnimationListener;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.BitmapUtil;
import com.cooingdv.rcufo.utils.Dbug;
import com.cooingdv.rcufo.utils.MusicUtils;
import com.cooingdv.rcufo.utils.RecognitionUtils;
import com.cooingdv.rcufo.utils.SoundUtils;
import com.cooingdv.rcufo.utils.StorageUtil;
import com.cooingdv.rcufo.utils.WifiIdUtils;
import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Objects;
import java.util.Timer;
import java.util.TimerTask;

/* JADX INFO: loaded from: classes2.dex */
public class DeviceBLFragment extends BaseFragment implements View.OnClickListener, AdapterView.OnItemClickListener, RockerView.OnShakeListener, GravityModel.OnOperationListener, TrackView.OnTrackListener, TrackAnimationListener.AnimatorTrackListener, OnMusicComposeListener, SeekBar.OnSeekBarChangeListener, View.OnTouchListener, OnMjpegListener, RockerView.OnAngleChangeListener {
    private static final long DEFAULT_VIDEO_SIZE = 31457280;
    private static final int MSG_GESTURE_TOAST = 43972;
    private static final int MSG_UPDATE_RECORDING_UI = 43971;
    private static final int OPERATION_ADD = 1;
    private static final int OPERATION_DEL = 0;
    private RelativeLayout LayoutControlMode;
    private TopListViewAdapter adapter;
    private ImageView air;
    private int airHeight;
    private int airWidth;
    private ViewPropertyAnimator animator;
    private AssetManager assetManager;
    private ImageView btnEmergencyStop;
    private ImageView btnGesture;
    private ImageView btnGravitySensor;
    private ImageView btnGyro;
    private ImageView btnLand;
    private ImageView btnMusic;
    private ImageView btnOrientation;
    private ImageView btnPortraitBack;
    private ImageView btnPortraitGesture;
    private ImageView btnPortraitMedia;
    private ImageView btnPortraitMenu;
    private ImageView btnPortraitPhoto;
    private ImageView btnPortraitRotate;
    private ImageView btnPortraitScreen;
    private ImageView btnPortraitSwitch;
    private ImageView btnPortraitVideo;
    private ImageView btnScale;
    private ImageView btnTakeoff;
    private ImageView btnTurn360;
    private ImageView btnVRMode;
    private Timer frameTimer;
    private Timer gestureTimer;
    private MyScaleView horizontalBar;
    private MyScaleView horizontalCenterBar;
    private boolean isLeftLimit;
    private boolean isMusicComposing;
    private boolean isRightLimit;
    private boolean isTakingControl;
    private ImageView ivBg;
    private ImageView ivBg2;
    private ImageView ivGestureType;
    private ImageView ivLeftBgRocker;
    private ImageView ivMVMode;
    private ImageView ivRecordNumber;
    private ImageView ivRightBgRocker;
    private LinearLayout layoutBtnPortrait;
    private RelativeLayout layoutControlRightDraw;
    private RelativeLayout layoutControlRightRocker;
    private LinearLayout layoutDownMenu;
    private LinearLayout layoutPortrait;
    private LinearLayout layoutScaleSeek;
    private RelativeLayout layoutVideoView;
    private LinearLayout layoutViewMode;
    private FlyController mFlyController;
    private ScreenSensorHelper mSensorHelper;
    private VerticalSeekBar mVerticalSeekBar;
    private byte[] mVideoData;
    private MjpegThread mjpegThread;
    private ImageView mjpegView;
    private ImageView mjpegView2;
    private GravityModel model;
    private String musicName;
    private String musicPath;
    private MusicUtils musicUtils;
    private MyTimer myTimer;
    private ProgressBar progressBarMusic;
    private RockerView rvHorizontal;
    private RockerView rvVertical;
    private String savePhotoName;
    private String savePhotoPath;
    private RelativeLayout scaleViewLayout1;
    private RelativeLayout scaleViewLayout2;
    private RelativeLayout scaleViewLayout3;
    private ScanFilesHelper scanFilesHelper;
    private float startX;
    private float startY;
    private HorizontalListView topListView;
    private TrackView trackView;
    private TextView tvPortraitTime;
    private TextView tvScale;
    private MyScaleView verticalBar;
    private VideoModel videoModel;
    private int noCardRecordMax = 30;
    private int deviceVideoTime = 0;
    private boolean noCardRecording = false;
    private boolean noCardTaking = false;
    private boolean isVarMode = false;
    private boolean isSupport = false;
    private int horizontalCurrentValue = 0;
    private int horizontalCenterCurrentValue = 0;
    private int verticalCurrentValue = 0;
    private int fakeResolutionType = 0;
    private int numPhoto = 0;
    private int numVideo = 0;
    private int palmCount = 0;
    private boolean isRecognition = false;
    private int[] recordNumber = {C3033R.mipmap.gesture_countdown_3, C3033R.mipmap.gesture_countdown_2, C3033R.mipmap.gesture_countdown_1};
    private int recordNumberIndex = 0;
    private float lastScaleX = 0.0f;
    private float lastScaleY = 0.0f;
    private int musicType = 0;
    private Handler mHandler = new Handler(new C30631());
    private int currPower = 4;
    ArrayList<String> topList = new ArrayList<>();
    ArrayList<String> topList2 = new ArrayList<>();
    private OnSocketListener mOnSocketListener = new C30653();

    @Override // com.cooingdv.rcufo.libs.RockerView.OnShakeListener
    public void direction(RockerView rockerView, RockerView.Direction direction, double d, int i, int i2) {
    }

    @Override // com.cooingdv.rcufo.libs.RockerView.OnAngleChangeListener
    public void onFinish() {
    }

    @Override // android.widget.SeekBar.OnSeekBarChangeListener
    public void onStartTrackingTouch(SeekBar seekBar) {
    }

    @Override // android.widget.SeekBar.OnSeekBarChangeListener
    public void onStopTrackingTouch(SeekBar seekBar) {
    }

    static /* synthetic */ int access$1308(DeviceBLFragment deviceBLFragment) {
        int i = deviceBLFragment.recordNumberIndex;
        deviceBLFragment.recordNumberIndex = i + 1;
        return i;
    }

    static /* synthetic */ int access$3708(DeviceBLFragment deviceBLFragment) {
        int i = deviceBLFragment.palmCount;
        deviceBLFragment.palmCount = i + 1;
        return i;
    }

    /* JADX INFO: renamed from: com.cooingdv.rcufo.fragment.DeviceBLFragment$1 */
    class C30631 implements Handler.Callback {
        C30631() {
        }

        /* JADX WARN: Can't fix incorrect switch cases order, some code will duplicate */
        @Override // android.os.Handler.Callback
        public boolean handleMessage(Message message) {
            if (DeviceBLFragment.this.getActivity() != null && DeviceBLFragment.this.isAdded() && message != null) {
                switch (message.what) {
                    case DeviceBLFragment.MSG_UPDATE_RECORDING_UI /* 43971 */:
                        if (DeviceBLFragment.this.myTimer != null && DeviceBLFragment.this.myTimer.isTimerRunning()) {
                            int iIntValue = ((Integer) message.obj).intValue();
                            String strShowRecordingTimeFormat = TimeFormater.showRecordingTimeFormat(iIntValue);
                            if (!TextUtils.isEmpty(strShowRecordingTimeFormat)) {
                                DeviceBLFragment.this.adapter.setTimer(strShowRecordingTimeFormat);
                                DeviceBLFragment.this.adapter.notifyDataSetChanged();
                            }
                            if (DeviceBLFragment.this.tvPortraitTime.getVisibility() == 0) {
                                DeviceBLFragment.this.tvPortraitTime.setText(strShowRecordingTimeFormat);
                            }
                            if (DeviceBLFragment.this.mFlyController.isMusicMode() && (iIntValue * 1000) + 2000 > DeviceBLFragment.this.musicUtils.getDuration()) {
                                DeviceBLFragment.this.stopNoCardRecording();
                            }
                        }
                        break;
                    case DeviceBLFragment.MSG_GESTURE_TOAST /* 43972 */:
                        if (DeviceBLFragment.this.isRecognition) {
                            return false;
                        }
                        int[] iArr = (int[]) message.obj;
                        int i = iArr[0];
                        DeviceBLFragment.this.isRecognition = true;
                        if (i != 2) {
                            if (i == 1) {
                                if (DeviceBLFragment.this.noCardRecording) {
                                    DeviceBLFragment.this.gestureRecogFrame(iArr);
                                    DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(2), 2, DeviceBLFragment.this.topListView.getItemIdAtPosition(2));
                                    DeviceBLFragment.this.mHandler.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.1.2
                                        @Override // java.lang.Runnable
                                        public void run() {
                                            DeviceBLFragment.this.isRecognition = false;
                                            DeviceBLFragment.this.layoutVideoView.removeAllViews();
                                        }
                                    }, 2000L);
                                } else {
                                    DeviceBLFragment.this.gestureRecogFrame(iArr);
                                    DeviceBLFragment.this.ivGestureType.setVisibility(0);
                                    DeviceBLFragment.this.ivGestureType.setImageResource(C3033R.mipmap.gesture_fist_red);
                                    DeviceBLFragment.this.ivRecordNumber.setVisibility(0);
                                    DeviceBLFragment.this.ivRecordNumber.setImageResource(DeviceBLFragment.this.recordNumber[DeviceBLFragment.this.recordNumberIndex]);
                                    DeviceBLFragment.access$1308(DeviceBLFragment.this);
                                    DeviceBLFragment.this.mHandler.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.1.3
                                        @Override // java.lang.Runnable
                                        public void run() {
                                            if (DeviceBLFragment.this.recordNumberIndex == 3) {
                                                DeviceBLFragment.this.ivGestureType.setVisibility(8);
                                                DeviceBLFragment.this.ivRecordNumber.setVisibility(8);
                                                DeviceBLFragment.this.layoutVideoView.removeAllViews();
                                                DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(2), 2, DeviceBLFragment.this.topListView.getItemIdAtPosition(2));
                                            } else {
                                                DeviceBLFragment.this.ivRecordNumber.setImageResource(DeviceBLFragment.this.recordNumber[DeviceBLFragment.this.recordNumberIndex]);
                                            }
                                            DeviceBLFragment.access$1308(DeviceBLFragment.this);
                                            if (DeviceBLFragment.this.recordNumberIndex > 3) {
                                                DeviceBLFragment.this.mHandler.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.1.3.1
                                                    @Override // java.lang.Runnable
                                                    public void run() {
                                                        DeviceBLFragment.this.isRecognition = false;
                                                        DeviceBLFragment.this.recordNumberIndex = 0;
                                                    }
                                                }, 2000L);
                                            } else {
                                                DeviceBLFragment.this.mHandler.postDelayed(this, 1000L);
                                            }
                                        }
                                    }, 1000L);
                                }
                            }
                        } else if (DeviceBLFragment.this.noCardTaking || DeviceBLFragment.this.noCardRecording) {
                            DeviceBLFragment.this.isRecognition = false;
                        } else {
                            DeviceBLFragment.this.gestureRecogFrame(iArr);
                            DeviceBLFragment.this.ivGestureType.setVisibility(0);
                            DeviceBLFragment.this.ivGestureType.setImageResource(C3033R.mipmap.gesture_rpalm_red);
                            DeviceBLFragment.this.ivRecordNumber.setVisibility(0);
                            DeviceBLFragment.this.ivRecordNumber.setImageResource(DeviceBLFragment.this.recordNumber[DeviceBLFragment.this.recordNumberIndex]);
                            DeviceBLFragment.access$1308(DeviceBLFragment.this);
                            DeviceBLFragment.this.mHandler.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.1.1
                                @Override // java.lang.Runnable
                                public void run() {
                                    if (DeviceBLFragment.this.recordNumberIndex == 3) {
                                        DeviceBLFragment.this.ivGestureType.setVisibility(8);
                                        DeviceBLFragment.this.ivRecordNumber.setVisibility(8);
                                        DeviceBLFragment.this.layoutVideoView.removeAllViews();
                                        DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(1), 1, DeviceBLFragment.this.topListView.getItemIdAtPosition(1));
                                    } else {
                                        DeviceBLFragment.this.ivRecordNumber.setImageResource(DeviceBLFragment.this.recordNumber[DeviceBLFragment.this.recordNumberIndex]);
                                    }
                                    DeviceBLFragment.access$1308(DeviceBLFragment.this);
                                    if (DeviceBLFragment.this.recordNumberIndex > 3) {
                                        DeviceBLFragment.this.mHandler.postDelayed(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.1.1.1
                                            @Override // java.lang.Runnable
                                            public void run() {
                                                DeviceBLFragment.this.isRecognition = false;
                                                DeviceBLFragment.this.recordNumberIndex = 0;
                                            }
                                        }, 2000L);
                                    } else {
                                        DeviceBLFragment.this.mHandler.postDelayed(this, 1000L);
                                    }
                                }
                            }, 1000L);
                        }
                        break;
                }
            }
            return false;
        }
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMjpegListener
    public void onFrame(final Bitmap bitmap) {
        this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.2
            @Override // java.lang.Runnable
            public void run() {
                DeviceBLFragment.this.mjpegView.setImageBitmap(bitmap);
                if (DeviceBLFragment.this.isVarMode) {
                    DeviceBLFragment.this.mjpegView2.setImageBitmap(bitmap);
                }
            }
        });
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate;
        if (PreferencesHelper.getSharedPreferences(getContext()).getBoolean(IConstants.RIGHT_HAND_MODE, false)) {
            viewInflate = layoutInflater.inflate(C3033R.layout.fragment_device_right_hand, viewGroup, false);
        } else {
            viewInflate = layoutInflater.inflate(C3033R.layout.fragment_device, viewGroup, false);
        }
        this.LayoutControlMode = (RelativeLayout) viewInflate.findViewById(C3033R.id.device_control_mode);
        this.layoutControlRightRocker = (RelativeLayout) viewInflate.findViewById(C3033R.id.view_control_right_rocker);
        this.layoutControlRightDraw = (RelativeLayout) viewInflate.findViewById(C3033R.id.view_control_right_draw);
        this.scaleViewLayout1 = (RelativeLayout) viewInflate.findViewById(C3033R.id.view_control_layout1);
        this.scaleViewLayout2 = (RelativeLayout) viewInflate.findViewById(C3033R.id.view_control_layout2);
        this.scaleViewLayout3 = (RelativeLayout) viewInflate.findViewById(C3033R.id.view_control_layout3);
        this.layoutViewMode = (LinearLayout) viewInflate.findViewById(C3033R.id.device_view_mode);
        this.layoutDownMenu = (LinearLayout) viewInflate.findViewById(C3033R.id.device_view_down_menu);
        this.topListView = (HorizontalListView) viewInflate.findViewById(C3033R.id.bar_device_top_list_view);
        this.layoutVideoView = (RelativeLayout) viewInflate.findViewById(C3033R.id.device_video_view_layout);
        this.ivBg = (ImageView) viewInflate.findViewById(C3033R.id.iv_bg);
        this.ivBg2 = (ImageView) viewInflate.findViewById(C3033R.id.iv_bg2);
        ImageView imageView = (ImageView) viewInflate.findViewById(C3033R.id.device_video_view);
        this.mjpegView = imageView;
        imageView.setOnTouchListener(this);
        this.mjpegView2 = (ImageView) viewInflate.findViewById(C3033R.id.device_video_view2);
        ImageView imageView2 = (ImageView) viewInflate.findViewById(C3033R.id.view_control_device_take_off);
        this.btnTakeoff = imageView2;
        imageView2.setOnClickListener(this);
        ImageView imageView3 = (ImageView) viewInflate.findViewById(C3033R.id.view_control_device_land);
        this.btnLand = imageView3;
        imageView3.setOnClickListener(this);
        ((ImageView) viewInflate.findViewById(C3033R.id.view_device_mode_headmode)).setOnClickListener(this);
        ImageView imageView4 = (ImageView) viewInflate.findViewById(C3033R.id.view_device_mode_turn360);
        this.btnTurn360 = imageView4;
        imageView4.setOnClickListener(this);
        ((ImageView) viewInflate.findViewById(C3033R.id.view_device_mode_track)).setOnClickListener(this);
        ImageView imageView5 = (ImageView) viewInflate.findViewById(C3033R.id.view_control_device_emergency_stop);
        this.btnEmergencyStop = imageView5;
        imageView5.setOnClickListener(this);
        ImageView imageView6 = (ImageView) viewInflate.findViewById(C3033R.id.view_device_mode_gravity_sensor);
        this.btnGravitySensor = imageView6;
        imageView6.setOnClickListener(this);
        ImageView imageView7 = (ImageView) viewInflate.findViewById(C3033R.id.view_device_mode_gyroscope);
        this.btnGyro = imageView7;
        imageView7.setOnClickListener(this);
        ImageView imageView8 = (ImageView) viewInflate.findViewById(C3033R.id.view_device_mode_gesture);
        this.btnGesture = imageView8;
        imageView8.setOnClickListener(this);
        this.ivRecordNumber = (ImageView) viewInflate.findViewById(C3033R.id.device_video_gesture_iv);
        this.ivGestureType = (ImageView) viewInflate.findViewById(C3033R.id.down_menu_im_gesture_type);
        ImageView imageView9 = (ImageView) viewInflate.findViewById(C3033R.id.view_device_mode_vr);
        this.btnVRMode = imageView9;
        imageView9.setOnClickListener(this);
        ImageView imageView10 = (ImageView) viewInflate.findViewById(C3033R.id.down_menu_btn_music);
        this.btnMusic = imageView10;
        imageView10.setOnClickListener(this);
        this.ivMVMode = (ImageView) viewInflate.findViewById(C3033R.id.device_video_mv_mode);
        ImageView imageView11 = (ImageView) viewInflate.findViewById(C3033R.id.down_menu_btn_scale);
        this.btnScale = imageView11;
        imageView11.setOnClickListener(this);
        ImageView imageView12 = (ImageView) viewInflate.findViewById(C3033R.id.down_menu_btn_orientation);
        this.btnOrientation = imageView12;
        imageView12.setOnClickListener(this);
        this.progressBarMusic = (ProgressBar) viewInflate.findViewById(C3033R.id.device_music_compose_pb);
        this.horizontalBar = (MyScaleView) viewInflate.findViewById(C3033R.id.view_control_device_horizontal_bar);
        View viewFindViewById = viewInflate.findViewById(C3033R.id.view_control_device_horizontal_del);
        View viewFindViewById2 = viewInflate.findViewById(C3033R.id.view_control_device_horizontal_add);
        this.horizontalCenterBar = (MyScaleView) viewInflate.findViewById(C3033R.id.view_control_device_horizontal_center_bar);
        View viewFindViewById3 = viewInflate.findViewById(C3033R.id.view_control_device_horizontal_left);
        View viewFindViewById4 = viewInflate.findViewById(C3033R.id.view_control_device_horizontal_right);
        this.verticalBar = (MyScaleView) viewInflate.findViewById(C3033R.id.view_control_device_vertical_bar);
        View viewFindViewById5 = viewInflate.findViewById(C3033R.id.view_control_device_vertical_del);
        View viewFindViewById6 = viewInflate.findViewById(C3033R.id.view_control_device_vertical_add);
        this.rvVertical = (RockerView) viewInflate.findViewById(C3033R.id.view_control_device_left_rocker);
        this.rvHorizontal = (RockerView) viewInflate.findViewById(C3033R.id.view_control_device_right_rocker);
        this.trackView = (TrackView) viewInflate.findViewById(C3033R.id.view_control_device_track_view);
        this.ivLeftBgRocker = (ImageView) viewInflate.findViewById(C3033R.id.view_control_device_left_iv);
        this.ivRightBgRocker = (ImageView) viewInflate.findViewById(C3033R.id.view_control_device_right_iv);
        this.layoutScaleSeek = (LinearLayout) viewInflate.findViewById(C3033R.id.device_scale_seek_layout);
        this.tvScale = (TextView) viewInflate.findViewById(C3033R.id.device_view_scale_tv);
        VerticalSeekBar verticalSeekBar = (VerticalSeekBar) viewInflate.findViewById(C3033R.id.device_view_scale_seek_progress);
        this.mVerticalSeekBar = verticalSeekBar;
        verticalSeekBar.setMax(50);
        this.mVerticalSeekBar.setOnSeekBarChangeListener(this);
        viewFindViewById.setOnClickListener(this);
        viewFindViewById2.setOnClickListener(this);
        viewFindViewById3.setOnClickListener(this);
        viewFindViewById4.setOnClickListener(this);
        viewFindViewById5.setOnClickListener(this);
        viewFindViewById6.setOnClickListener(this);
        this.topListView.setOnItemClickListener(this);
        this.rvVertical.setFixHeight(false);
        this.rvVertical.setOnShakeListener(RockerView.DirectionMode.DIRECTION_4_ROTATE_45, this);
        this.rvVertical.setOnAngleChangeListener(this);
        this.rvVertical.setCallBackMode(RockerView.CallBackMode.CALL_BACK_MODE_STATE_DISTANCE_CHANGE);
        this.rvHorizontal.setFixHeight(true);
        this.rvHorizontal.setOnShakeListener(RockerView.DirectionMode.DIRECTION_4_ROTATE_45, this);
        this.rvHorizontal.setOnAngleChangeListener(this);
        this.rvHorizontal.setCallBackMode(RockerView.CallBackMode.CALL_BACK_MODE_STATE_DISTANCE_CHANGE);
        this.rvHorizontal.setIsJohnCustomMode(true);
        this.trackView.setOnTrackListener(this);
        this.layoutPortrait = (LinearLayout) viewInflate.findViewById(C3033R.id.device_portrait_layout);
        this.layoutBtnPortrait = (LinearLayout) viewInflate.findViewById(C3033R.id.view_orientation_btn_layout);
        this.btnPortraitBack = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_back);
        this.btnPortraitSwitch = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_switch);
        this.btnPortraitMedia = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_media);
        this.btnPortraitMenu = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_menu);
        this.btnPortraitPhoto = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_take_photo);
        this.btnPortraitVideo = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_record);
        this.btnPortraitScreen = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_screen);
        this.btnPortraitGesture = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_gesture);
        this.btnPortraitRotate = (ImageView) viewInflate.findViewById(C3033R.id.view_portrait_btn_rotate);
        this.tvPortraitTime = (TextView) viewInflate.findViewById(C3033R.id.view_portrait_tv_time);
        this.btnPortraitBack.setOnClickListener(this);
        this.btnPortraitSwitch.setOnClickListener(this);
        this.btnPortraitMedia.setOnClickListener(this);
        this.btnPortraitMenu.setOnClickListener(this);
        this.btnPortraitPhoto.setOnClickListener(this);
        this.btnPortraitVideo.setOnClickListener(this);
        this.btnPortraitScreen.setOnClickListener(this);
        this.btnPortraitGesture.setOnClickListener(this);
        this.btnPortraitRotate.setOnClickListener(this);
        GravityModel gravityModel = new GravityModel(this);
        this.model = gravityModel;
        gravityModel.setOnOperationListener(this);
        this.videoModel = new VideoModel(this);
        this.musicUtils = new MusicUtils(getActivity());
        this.assetManager = getActivity().getAssets();
        return viewInflate;
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() != null) {
            MjpegThread mjpegThread = new MjpegThread(getActivity());
            this.mjpegThread = mjpegThread;
            mjpegThread.setOnMjpegListener(this);
            this.mjpegThread.start();
            initListView();
            setResolution(MainApplication.getInstance().getFakeResolutionNumber());
            this.mjpegView.setVisibility(8);
            this.mjpegView2.setVisibility(8);
            this.mFlyController = new FlyController(this.mHandler);
            if (this.scanFilesHelper == null) {
                this.scanFilesHelper = new ScanFilesHelper(getActivity().getApplicationContext());
            }
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onResume() {
        super.onResume();
        initStatus();
        startServer();
    }

    private void startServer() {
        SocketClient.getInstance().setOnSocketListener(this.mOnSocketListener);
    }

    @Override // androidx.fragment.app.Fragment
    public void onStop() {
        super.onStop();
        cleanStatus();
    }

    public void cleanStatus() {
        if (this.mjpegView.getVisibility() == 0) {
            this.mjpegView.setVisibility(8);
        }
        if (this.mjpegView2.getVisibility() == 0) {
            this.mjpegView2.setVisibility(8);
        }
        if (this.noCardRecording) {
            this.noCardRecording = false;
            stopNoCardRecording();
            TopListViewAdapter topListViewAdapter = this.adapter;
            if (topListViewAdapter != null) {
                topListViewAdapter.setRecordVideo(false);
            }
        }
        if (this.noCardTaking) {
            this.noCardTaking = false;
        }
        FlyController flyController = this.mFlyController;
        if (flyController != null) {
            flyController.setGravitySensor(false);
            this.model.unRegisterListener();
            this.rvHorizontal.setFixHeight(true);
            this.rvHorizontal.setIsGravityMode(false);
            this.btnGravitySensor.setImageResource(C3033R.drawable.drawable_gravity_icon);
        }
        TopListViewAdapter topListViewAdapter2 = this.adapter;
        if (topListViewAdapter2 != null) {
            topListViewAdapter2.notifyDataSetChanged();
        }
        Timer timer = this.gestureTimer;
        if (timer != null) {
            timer.cancel();
            this.gestureTimer = null;
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
        if (getActivity() != null && getActivity().getRequestedOrientation() == 1) {
            getActivity().setRequestedOrientation(0);
        }
        if (this.mFlyController.isControlMode()) {
            updateModeUI();
        }
        this.deviceVideoTime = 0;
        MyTimer myTimer = this.myTimer;
        if (myTimer != null) {
            myTimer.stopTimer();
            this.myTimer = null;
        }
        Handler handler = this.mHandler;
        if (handler != null) {
            handler.removeCallbacksAndMessages(null);
        }
        MjpegThread mjpegThread = this.mjpegThread;
        if (mjpegThread != null) {
            mjpegThread.release();
        }
        ScanFilesHelper scanFilesHelper = this.scanFilesHelper;
        if (scanFilesHelper != null) {
            scanFilesHelper.release();
            this.scanFilesHelper = null;
        }
        GravityModel gravityModel = this.model;
        if (gravityModel != null) {
            gravityModel.unRegisterListener();
        }
        if (this.videoModel.isRecording()) {
            this.videoModel.stopRecorder();
        }
        Timer timer = this.frameTimer;
        if (timer != null) {
            timer.cancel();
            this.frameTimer = null;
        }
        ScreenSensorHelper screenSensorHelper = this.mSensorHelper;
        if (screenSensorHelper != null) {
            screenSensorHelper.disable();
            this.mSensorHelper = null;
        }
    }

    /* JADX WARN: Can't fix incorrect switch cases order, some code will duplicate */
    /* JADX WARN: Code duplicated, block: B:88:0x0232  */
    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (view == null || getActivity() == null) {
            return;
        }
        int id = view.getId();
        if (id == C3033R.id.view_control_device_take_off) {
            this.mFlyController.setFastFly((ImageView) view);
            return;
        }
        if (id == C3033R.id.view_control_device_vertical_add) {
            updateAdjustBar(this.verticalBar, 1);
            return;
        }
        if (id == C3033R.id.view_control_device_vertical_del) {
            updateAdjustBar(this.verticalBar, 0);
            return;
        }
        switch (id) {
            case C3033R.id.down_menu_btn_music /* 2131296580 */:
                startActivityForResult(new Intent(getActivity(), (Class<?>) MusicActivity.class), 2002);
                return;
            case C3033R.id.down_menu_btn_orientation /* 2131296581 */:
                break;
            case C3033R.id.down_menu_btn_scale /* 2131296582 */:
                if (this.layoutScaleSeek.getVisibility() == 0) {
                    this.layoutScaleSeek.setVisibility(8);
                    ((ImageView) view).setImageResource(C3033R.drawable.drawable_scale);
                    return;
                } else {
                    this.layoutScaleSeek.setVisibility(0);
                    ((ImageView) view).setImageResource(C3033R.drawable.drawable_scale_yellow);
                    return;
                }
            default:
                switch (id) {
                    case C3033R.id.view_control_device_emergency_stop /* 2131297418 */:
                        this.mFlyController.setEmergencyStop((ImageView) view);
                        return;
                    case C3033R.id.view_control_device_horizontal_add /* 2131297419 */:
                        updateAdjustBar(this.horizontalBar, 1);
                        return;
                    default:
                        switch (id) {
                            case C3033R.id.view_control_device_horizontal_del /* 2131297422 */:
                                updateAdjustBar(this.horizontalBar, 0);
                                return;
                            case C3033R.id.view_control_device_horizontal_left /* 2131297423 */:
                                updateAdjustBar(this.horizontalCenterBar, 0);
                                return;
                            case C3033R.id.view_control_device_horizontal_right /* 2131297424 */:
                                updateAdjustBar(this.horizontalCenterBar, 1);
                                return;
                            case C3033R.id.view_control_device_land /* 2131297425 */:
                                this.mFlyController.setFastDrop((ImageView) view);
                                return;
                            default:
                                switch (id) {
                                    case C3033R.id.view_device_mode_gesture /* 2131297440 */:
                                        openGesture();
                                        break;
                                    case C3033R.id.view_device_mode_gravity_sensor /* 2131297441 */:
                                        FlyController flyController = this.mFlyController;
                                        if (flyController != null) {
                                            flyController.setGravitySensor(!flyController.isGravitySensor());
                                            if (this.mFlyController.isGravitySensor()) {
                                                ((ImageView) view).setImageResource(C3033R.drawable.drawable_gravity_yellow);
                                                this.model.registerSensorListener();
                                                this.rvHorizontal.setIsGravityMode(true);
                                            } else {
                                                ((ImageView) view).setImageResource(C3033R.drawable.drawable_gravity_icon);
                                                this.model.unRegisterListener();
                                                this.rvHorizontal.setIsGravityMode(false);
                                                this.rvHorizontal.setFixHeight(true);
                                                FlyController flyController2 = this.mFlyController;
                                                Objects.requireNonNull(flyController2);
                                                flyController2.setControlByte1(128);
                                                FlyController flyController3 = this.mFlyController;
                                                Objects.requireNonNull(flyController3);
                                                flyController3.setControlByte2(128);
                                            }
                                        }
                                        break;
                                    case C3033R.id.view_device_mode_gyroscope /* 2131297442 */:
                                        this.mFlyController.setGyroCorrection((ImageView) view);
                                        break;
                                    case C3033R.id.view_device_mode_headmode /* 2131297443 */:
                                        this.mFlyController.setNoHeadMode((ImageView) view);
                                        break;
                                    case C3033R.id.view_device_mode_track /* 2131297444 */:
                                        FlyController flyController4 = this.mFlyController;
                                        if (flyController4 != null) {
                                            flyController4.setTrackMode(true ^ flyController4.isTrackMode());
                                            if (this.mFlyController.isTrackMode()) {
                                                ((ImageView) view).setImageResource(C3033R.drawable.drawable_track_yellow);
                                                this.layoutControlRightRocker.setVisibility(8);
                                                this.layoutControlRightDraw.setVisibility(0);
                                            } else {
                                                ((ImageView) view).setImageResource(C3033R.drawable.drawable_track_icon);
                                                this.layoutControlRightRocker.setVisibility(0);
                                                this.layoutControlRightDraw.setVisibility(8);
                                                ViewPropertyAnimator viewPropertyAnimator = this.animator;
                                                if (viewPropertyAnimator != null) {
                                                    viewPropertyAnimator.cancel();
                                                }
                                            }
                                        }
                                        break;
                                    case C3033R.id.view_device_mode_turn360 /* 2131297445 */:
                                        this.mFlyController.setCircleTurn((ImageView) view);
                                        break;
                                    case C3033R.id.view_device_mode_vr /* 2131297446 */:
                                        if (this.isVarMode) {
                                            this.isVarMode = false;
                                            ((ImageView) view).setImageResource(C3033R.drawable.drawable_vr_yellow);
                                            this.mjpegView2.setVisibility(8);
                                            this.ivBg2.setVisibility(8);
                                            this.mjpegView.setScaleType(ImageView.ScaleType.FIT_XY);
                                            if (this.mFlyController.isControlMode()) {
                                                this.LayoutControlMode.setVisibility(0);
                                            }
                                        } else {
                                            this.mjpegView.setScaleType(ImageView.ScaleType.FIT_CENTER);
                                            this.ivBg2.setVisibility(0);
                                            if (!SocketClient.getInstance().isActive()) {
                                                this.ivBg2.setVisibility(0);
                                            }
                                            this.isVarMode = true;
                                            ((ImageView) view).setImageResource(C3033R.drawable.drawable_vr);
                                            FlyController flyController5 = this.mFlyController;
                                            if (flyController5 != null) {
                                                if (flyController5.isControlMode()) {
                                                    this.LayoutControlMode.setVisibility(8);
                                                }
                                                if (this.mFlyController.isGravitySensor()) {
                                                    this.mFlyController.setGravitySensor(false);
                                                    this.model.unRegisterListener();
                                                    this.rvHorizontal.setIsGravityMode(false);
                                                    this.rvHorizontal.setFixHeight(true);
                                                }
                                            }
                                        }
                                        break;
                                    default:
                                        switch (id) {
                                            case C3033R.id.view_portrait_btn_back /* 2131297450 */:
                                                getActivity().onBackPressed();
                                                break;
                                            case C3033R.id.view_portrait_btn_gesture /* 2131297451 */:
                                                openGesture();
                                                break;
                                            case C3033R.id.view_portrait_btn_media /* 2131297452 */:
                                                if (!this.noCardRecording) {
                                                    stopNoCardRecording();
                                                    Intent intent = new Intent(getActivity(), (Class<?>) BrowseFileActivity.class);
                                                    intent.putExtra(IConstants.KEY_DIR_TYPE, IConstants.VIEW_FRONT);
                                                    startActivity(intent);
                                                    break;
                                                }
                                                break;
                                            case C3033R.id.view_portrait_btn_menu /* 2131297453 */:
                                                if (this.layoutBtnPortrait.getVisibility() == 0) {
                                                    this.layoutBtnPortrait.setVisibility(4);
                                                } else {
                                                    this.layoutBtnPortrait.setVisibility(0);
                                                }
                                                break;
                                            case C3033R.id.view_portrait_btn_record /* 2131297454 */:
                                                if (!BufChangeHex.isFastDoubleClick(1000)) {
                                                    if (this.noCardRecording) {
                                                        stopNoCardRecording();
                                                        break;
                                                    } else if (!this.isMusicComposing) {
                                                        startNoCardRecording();
                                                        break;
                                                    }
                                                }
                                                break;
                                            case C3033R.id.view_portrait_btn_rotate /* 2131297455 */:
                                                if (!SocketClient.getInstance().isActive()) {
                                                    showShortToast(C3033R.string.connect_device_tip);
                                                } else if (this.mjpegView != null) {
                                                    MjpegThread mjpegThread = this.mjpegThread;
                                                    mjpegThread.setTurnBitmap(!mjpegThread.getTurnBitmap());
                                                    PreferencesHelper.putBooleanValue(getActivity(), IConstants.SCREEN_DIRECTION_SHARE_KEY, this.mjpegThread.getTurnBitmap());
                                                    this.adapter.setTurn180(this.mjpegThread.getTurnBitmap());
                                                }
                                                break;
                                            case C3033R.id.view_portrait_btn_switch /* 2131297457 */:
                                                if (SocketClient.getInstance().isActive()) {
                                                    SocketClient.getInstance().switchCamera();
                                                }
                                                break;
                                            case C3033R.id.view_portrait_btn_take_photo /* 2131297458 */:
                                                if (!BufChangeHex.isFastDoubleClick(500)) {
                                                    if (this.noCardTaking) {
                                                        showLongToast(getString(C3033R.string.taking_photo));
                                                    } else if (!this.noCardRecording) {
                                                        startNoCardTaking();
                                                    } else {
                                                        showShortToast(C3033R.string.no_card_taking_video_error);
                                                    }
                                                }
                                                break;
                                        }
                                        break;
                                }
                                return;
                        }
                }
        }
        if (this.noCardRecording) {
            stopNoCardRecording();
        }
        if (getActivity().getRequestedOrientation() == 1) {
            getActivity().setRequestedOrientation(0);
            this.mjpegThread.setPortrait(false);
        } else {
            getActivity().setRequestedOrientation(1);
            this.mjpegThread.setPortrait(true);
        }
    }

    @Override // android.widget.AdapterView.OnItemClickListener
    public void onItemClick(AdapterView<?> adapterView, View view, int i, long j) {
        FlyController flyController;
        if (this.adapter == null || getActivity() == null) {
            return;
        }
        String str = (String) this.adapter.getItem(i);
        if (TextUtils.isEmpty(str)) {
            return;
        }
        if (str.equals(getString(C3033R.string.tab_control_mode))) {
            updateModeUI();
            return;
        }
        if (str.equals(getString(C3033R.string.tab_take_photo))) {
            if (BufChangeHex.isFastDoubleClick(500)) {
                return;
            }
            if (this.noCardTaking) {
                showLongToast(getString(C3033R.string.taking_photo));
                return;
            } else if (!this.noCardRecording) {
                startNoCardTaking();
                return;
            } else {
                showShortToast(C3033R.string.no_card_taking_video_error);
                return;
            }
        }
        if (str.equals(getString(C3033R.string.tab_record_video))) {
            if (BufChangeHex.isFastDoubleClick(1000)) {
                return;
            }
            if (this.noCardRecording) {
                Dbug.m13285e(this.TAG, "停止录制视频");
                stopNoCardRecording();
                return;
            } else {
                if (this.isMusicComposing) {
                    return;
                }
                startNoCardRecording();
                return;
            }
        }
        if (str.equals(getString(C3033R.string.tab_media_library))) {
            if (this.noCardRecording) {
                return;
            }
            stopNoCardRecording();
            Intent intent = new Intent(getActivity(), (Class<?>) BrowseFileActivity.class);
            intent.putExtra(IConstants.KEY_DIR_TYPE, IConstants.VIEW_FRONT);
            startActivity(intent);
            return;
        }
        if (str.equals(getString(C3033R.string.tab_power))) {
            int i2 = this.currPower;
            if (i2 == 4) {
                this.currPower = 9;
            } else if (i2 == 9) {
                this.currPower = 14;
            } else if (i2 == 14) {
                this.currPower = 4;
            }
            this.adapter.setCurrPower(this.currPower);
            this.adapter.notifyDataSetChanged();
            return;
        }
        if (str.equals(getString(C3033R.string.tab_down_menu))) {
            TopListViewAdapter topListViewAdapter = this.adapter;
            topListViewAdapter.setMenuOpen(!topListViewAdapter.isMenuOpen());
            this.adapter.notifyDataSetChanged();
            if (this.adapter.isMenuOpen()) {
                this.layoutDownMenu.setVisibility(0);
                return;
            } else {
                this.layoutDownMenu.setVisibility(8);
                return;
            }
        }
        if (str.equals(getString(C3033R.string.tab_fixed_height))) {
            if (SocketClient.getInstance().getDeviceType() == 2 || (flyController = this.mFlyController) == null) {
                return;
            }
            flyController.setFixedHeightMode(!flyController.isFixedHeightMode());
            if (this.mFlyController.isFixedHeightMode()) {
                this.rvVertical.setFixHeight(true);
                this.adapter.setFixedHeightMode(true);
                ((ImageView) view).setImageResource(C3033R.drawable.drawable_fixed_height_yellow);
                updateFixHeightUI(true);
                PreferencesHelper.putBooleanValue(getActivity(), IConstants.FIX_HEIGHT_SHARE_KEY, true);
                FlyController flyController2 = this.mFlyController;
                Objects.requireNonNull(flyController2);
                flyController2.setControlAccelerator(128);
            } else {
                this.rvVertical.setFixHeight(false);
                this.adapter.setFixedHeightMode(false);
                ((ImageView) view).setImageResource(C3033R.drawable.drawable_fixed_height);
                updateFixHeightUI(false);
                PreferencesHelper.putBooleanValue(getActivity(), IConstants.FIX_HEIGHT_SHARE_KEY, false);
                this.mFlyController.setControlAccelerator(0);
            }
            this.adapter.notifyDataSetChanged();
            return;
        }
        if (str.equals(getString(C3033R.string.tab_turn_180))) {
            if (!SocketClient.getInstance().isActive()) {
                showShortToast(C3033R.string.connect_device_tip);
                return;
            } else {
                if (this.mjpegView != null) {
                    MjpegThread mjpegThread = this.mjpegThread;
                    mjpegThread.setTurnBitmap(!mjpegThread.getTurnBitmap());
                    PreferencesHelper.putBooleanValue(getActivity(), IConstants.SCREEN_DIRECTION_SHARE_KEY, this.mjpegThread.getTurnBitmap());
                    this.adapter.setTurn180(this.mjpegThread.getTurnBitmap());
                    return;
                }
                return;
            }
        }
        if (str.equals(getString(C3033R.string.tab_camera_switch))) {
            if (SocketClient.getInstance().isActive()) {
                SocketClient.getInstance().switchCamera();
            }
        } else if (str.equals(getString(C3033R.string.tab_turn_back))) {
            getActivity().onBackPressed();
        } else {
            showShortToast(C3033R.string.no_function_tip);
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void updateFixHeightUI(boolean z) {
        if (z) {
            this.btnTakeoff.setVisibility(0);
            this.btnEmergencyStop.setVisibility(0);
            this.btnLand.setVisibility(0);
        } else {
            this.btnTakeoff.setVisibility(8);
            this.btnEmergencyStop.setVisibility(8);
            this.btnLand.setVisibility(8);
        }
    }

    @Override // com.cooingdv.rcufo.libs.RockerView.OnShakeListener
    public void onShakeStart(RockerView rockerView) {
        if (rockerView == this.rvVertical && this.ivLeftBgRocker.getVisibility() != 0) {
            this.ivLeftBgRocker.setVisibility(0);
            this.ivLeftBgRocker.setImageResource(C3033R.mipmap.joystick_limtlinegreen);
        }
        if (rockerView != this.rvHorizontal || this.ivRightBgRocker.getVisibility() == 0) {
            return;
        }
        this.ivRightBgRocker.setVisibility(0);
        this.ivRightBgRocker.setImageResource(C3033R.mipmap.joystick_limtlinegreen);
    }

    /* JADX WARN: Code duplicated, block: B:33:0x0108  */
    /* JADX WARN: Code duplicated, block: B:40:0x012c  */
    /* JADX WARN: Code duplicated, block: B:42:0x013b  */
    /* JADX WARN: Code duplicated, block: B:49:0x014a  */
    /* JADX WARN: Code duplicated, block: B:54:0x016e  */
    @Override // com.cooingdv.rcufo.libs.RockerView.OnShakeListener
    public void onMove(RockerView rockerView, float f, float f2, int i) {
        int i2;
        if (this.mFlyController.isCircleTurnEnd()) {
            return;
        }
        if (rockerView == this.rvVertical) {
            float f3 = i;
            int i3 = ((int) ((f / f3) * 127.0f)) + (this.horizontalCurrentValue * 4);
            Objects.requireNonNull(this.mFlyController);
            Objects.requireNonNull(this.mFlyController);
            this.mFlyController.setControlAccelerator(((int) ((f2 / f3) * 127.0f)) + 128);
            this.mFlyController.setControlTurn(i3 + 128);
            if (this.isLeftLimit) {
                if (Math.abs(f) / rockerView.getRegionRadius() < 1.0f && Math.abs(f2) / rockerView.getRegionRadius() < 1.0f) {
                    this.isLeftLimit = false;
                    this.ivLeftBgRocker.setImageResource(C3033R.mipmap.joystick_limtlinegreen);
                }
            } else if (Math.abs(f) / rockerView.getRegionRadius() >= 1.0f || Math.abs(f2) / rockerView.getRegionRadius() >= 1.0f) {
                this.isLeftLimit = true;
                this.ivLeftBgRocker.setImageResource(C3033R.mipmap.joystick_limtline);
            }
        }
        if (rockerView == this.rvHorizontal) {
            float f4 = i;
            float halfLen = getHalfLen();
            int i4 = (int) ((f / f4) * halfLen);
            int i5 = (int) ((f2 / f4) * halfLen);
            int i6 = this.currPower;
            if (i6 == 4) {
                int i7 = i4 + (this.horizontalCenterCurrentValue * 2);
                Objects.requireNonNull(this.mFlyController);
                i4 = i7 + 128;
                i2 = i5 + (this.verticalCurrentValue * 2);
                Objects.requireNonNull(this.mFlyController);
            } else if (i6 == 9) {
                int i8 = i4 + (this.horizontalCenterCurrentValue * 3);
                Objects.requireNonNull(this.mFlyController);
                i4 = i8 + 128;
                i2 = i5 + (this.verticalCurrentValue * 3);
                Objects.requireNonNull(this.mFlyController);
            } else {
                if (i6 == 14) {
                    int i9 = i4 + (this.horizontalCenterCurrentValue * 4);
                    Objects.requireNonNull(this.mFlyController);
                    i4 = i9 + 128;
                    i2 = i5 + (this.verticalCurrentValue * 4);
                    Objects.requireNonNull(this.mFlyController);
                }
                this.mFlyController.setControlByte1(i4);
                this.mFlyController.setControlByte2(i5);
                if (this.mFlyController.isCircleTurn()) {
                    if (Math.abs(f) / rockerView.getRegionRadius() <= 0.7d && f2 > -30.0f && f2 < 30.0f) {
                        turn360(1, f);
                    } else if (Math.abs(f2) / rockerView.getRegionRadius() > 0.7d && f > -30.0f && f < 30.0f) {
                        turn360(2, f2);
                    }
                }
                if (!this.isRightLimit) {
                    if (Math.abs(f) / rockerView.getRegionRadius() < 1.0f || Math.abs(f2) / rockerView.getRegionRadius() >= 1.0f) {
                    }
                    this.isRightLimit = false;
                    this.ivRightBgRocker.setImageResource(C3033R.mipmap.joystick_limtlinegreen);
                    return;
                }
                if (Math.abs(f) / rockerView.getRegionRadius() < 1.0f || Math.abs(f2) / rockerView.getRegionRadius() >= 1.0f) {
                    this.isRightLimit = true;
                    this.ivRightBgRocker.setImageResource(C3033R.mipmap.joystick_limtline);
                }
                return;
            }
            i5 = i2 + 128;
            this.mFlyController.setControlByte1(i4);
            this.mFlyController.setControlByte2(i5);
            if (this.mFlyController.isCircleTurn()) {
                if (Math.abs(f) / rockerView.getRegionRadius() <= 0.7d) {
                    if (Math.abs(f2) / rockerView.getRegionRadius() > 0.7d) {
                        turn360(2, f2);
                    }
                } else if (Math.abs(f2) / rockerView.getRegionRadius() > 0.7d) {
                    turn360(2, f2);
                }
            }
            if (!this.isRightLimit) {
                if (Math.abs(f) / rockerView.getRegionRadius() < 1.0f) {
                }
            } else {
                if (Math.abs(f) / rockerView.getRegionRadius() < 1.0f) {
                }
                this.isRightLimit = true;
                this.ivRightBgRocker.setImageResource(C3033R.mipmap.joystick_limtline);
            }
        }
    }

    private void turn360(int i, float f) {
        this.mFlyController.setCircleTurn(this.btnTurn360);
        if (i == 1) {
            FlyController flyController = this.mFlyController;
            Objects.requireNonNull(flyController);
            flyController.setControlByte1(f <= 0.0f ? 1 : 255);
        } else {
            FlyController flyController2 = this.mFlyController;
            Objects.requireNonNull(flyController2);
            flyController2.setControlByte2(f <= 0.0f ? 1 : 255);
        }
        this.mFlyController.setCircleTurnEnd();
    }

    private int getHalfLen() {
        int i = this.currPower;
        if (i != 9) {
            return i != 14 ? 40 : 127;
        }
        return 60;
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityResult(int i, int i2, Intent intent) {
        if (i == 2002 && i2 == -1) {
            this.musicType = intent.getIntExtra("choose", 0);
            this.musicPath = intent.getStringExtra("path");
            this.musicName = intent.getStringExtra("name");
            this.videoModel.setType(this.musicType);
            if (this.musicType == 0) {
                if (this.mFlyController.isMusicMode()) {
                    this.mFlyController.setMusicMode(false);
                    this.btnMusic.setImageResource(C3033R.drawable.drawable_music);
                    this.videoModel.setOnMusicComposeListener(null);
                    this.ivMVMode.setVisibility(8);
                    return;
                }
                return;
            }
            if (!this.mFlyController.isMusicMode()) {
                this.mFlyController.setMusicMode(true);
                this.btnMusic.setImageResource(C3033R.drawable.drawable_music_yellow);
                this.videoModel.setOnMusicComposeListener(this);
                this.ivMVMode.setVisibility(0);
            }
            if (this.musicType == 3 && !TextUtils.isEmpty(this.musicPath)) {
                this.videoModel.setMusicPath(this.musicPath);
                return;
            }
            int i3 = this.musicType;
            if ((i3 == 1 || i3 == 2) && !TextUtils.isEmpty(this.musicName)) {
                this.videoModel.setName(this.musicName);
            }
        }
    }

    @Override // com.cooingdv.rcufo.models.GravityModel.OnOperationListener
    public void onChange(int i, int i2) {
        if (this.rvHorizontal == null || !this.mFlyController.isControlMode()) {
            return;
        }
        this.rvHorizontal.setPosition(i, i2);
    }

    private void initListView() {
        int i;
        if (getActivity() != null) {
            String[] stringArray = getResources().getStringArray(C3033R.array.device_top_list);
            this.topList.clear();
            Collections.addAll(this.topList, stringArray);
            HashMap map = new HashMap();
            for (String str : this.topList) {
                if (!TextUtils.isEmpty(str)) {
                    if (str.equals(getString(C3033R.string.tab_take_photo))) {
                        i = C3033R.drawable.drawable_take_photo;
                    } else if (str.equals(getString(C3033R.string.tab_record_video))) {
                        i = C3033R.drawable.drawable_video;
                    } else if (str.equals(getString(C3033R.string.tab_power))) {
                        i = C3033R.mipmap.icon_power_30;
                    } else if (str.equals(getString(C3033R.string.tab_gravity_sensor))) {
                        i = C3033R.drawable.drawable_gravity_icon;
                    } else if (str.equals(getString(C3033R.string.tab_control_mode))) {
                        FlyController flyController = this.mFlyController;
                        i = (flyController == null || !flyController.isControlMode()) ? C3033R.mipmap.icon_control_model_off : C3033R.mipmap.icon_control_model_on;
                    } else if (str.equals(getString(C3033R.string.tab_gyroscope_correction))) {
                        i = C3033R.drawable.drawable_gyr_icon;
                    } else if (str.equals(getString(C3033R.string.tab_camera_switch))) {
                        i = C3033R.drawable.drawable_camera_switch;
                    } else if (str.equals(getString(C3033R.string.tab_turn_180))) {
                        i = C3033R.drawable.drawable_turn_screen_icon;
                    } else if (str.equals(getString(C3033R.string.tab_media_library))) {
                        i = C3033R.drawable.drawable_icon_media;
                    } else if (str.equals(getString(C3033R.string.tab_down_menu))) {
                        i = C3033R.drawable.drawable_down_menu;
                    } else if (str.equals(getString(C3033R.string.tab_fixed_height))) {
                        FlyController flyController2 = this.mFlyController;
                        i = (flyController2 == null || !flyController2.isFixedHeightMode()) ? C3033R.drawable.drawable_fixed_height : C3033R.drawable.drawable_fixed_height_yellow;
                    } else {
                        i = str.equals(getString(C3033R.string.tab_turn_back)) ? C3033R.mipmap.play_back_icon : -1;
                    }
                    if (i != -1) {
                        map.put(str, Integer.valueOf(i));
                    }
                }
            }
            TopListViewAdapter topListViewAdapter = new TopListViewAdapter(getContext(), this.topList, map);
            this.adapter = topListViewAdapter;
            this.topListView.setAdapter((ListAdapter) topListViewAdapter);
        }
    }

    private void updateAdjustBar(MyScaleView myScaleView, int i) {
        boolean z = PreferencesHelper.getSharedPreferences(getContext()).getBoolean(IConstants.FINE_TUNE_PARAMS, false);
        if (myScaleView == null || z) {
            return;
        }
        int currentValue = myScaleView.getCurrentValue();
        int maxValue = myScaleView.getMaxValue();
        boolean z2 = true;
        if (i != 0) {
            if (i == 1 && currentValue < maxValue) {
                currentValue++;
            }
        } else if (currentValue > 0) {
            currentValue--;
        }
        if (currentValue != 12 && currentValue != 0 && currentValue != 24) {
            z2 = false;
        }
        SoundUtils.didiSound(z2, getActivity());
        myScaleView.setCurrentValue(currentValue);
        if (myScaleView == this.horizontalBar) {
            if (currentValue < 12) {
                this.horizontalCurrentValue = -(12 - currentValue);
                return;
            } else if (currentValue > 12) {
                this.horizontalCurrentValue = currentValue - 12;
                return;
            } else {
                this.horizontalCurrentValue = 0;
                return;
            }
        }
        if (myScaleView == this.horizontalCenterBar) {
            if (currentValue < 12) {
                this.horizontalCenterCurrentValue = -(12 - currentValue);
                return;
            } else if (currentValue > 12) {
                this.horizontalCenterCurrentValue = currentValue - 12;
                return;
            } else {
                this.horizontalCenterCurrentValue = 0;
                return;
            }
        }
        if (myScaleView == this.verticalBar) {
            if (currentValue < 12) {
                this.verticalCurrentValue = 12 - currentValue;
            } else if (currentValue > 12) {
                this.verticalCurrentValue = -(currentValue - 12);
            } else {
                this.verticalCurrentValue = 0;
            }
        }
    }

    private void updateModeUI() {
        boolean zIsControlMode = this.mFlyController.isControlMode();
        TopListViewAdapter topListViewAdapter = this.adapter;
        topListViewAdapter.setControlMode(!topListViewAdapter.isControlMode());
        this.adapter.notifyDataSetChanged();
        Dbug.m13285e(this.TAG, "isControlMode=" + zIsControlMode);
        if (!zIsControlMode) {
            if (this.LayoutControlMode.getVisibility() != 0) {
                this.LayoutControlMode.setVisibility(0);
            }
            if (!this.mFlyController.isFixedHeightMode()) {
                this.rvVertical.setFixHeight(false);
                this.mFlyController.setControlAccelerator(0);
            } else {
                FlyController flyController = this.mFlyController;
                Objects.requireNonNull(flyController);
                flyController.setControlAccelerator(128);
            }
            this.layoutViewMode.setVisibility(0);
            this.mFlyController.setController(true);
            return;
        }
        if (this.LayoutControlMode.getVisibility() != 8) {
            this.LayoutControlMode.setVisibility(8);
        }
        this.layoutViewMode.setVisibility(8);
        ViewPropertyAnimator viewPropertyAnimator = this.animator;
        if (viewPropertyAnimator != null) {
            viewPropertyAnimator.cancel();
        }
        this.mFlyController.setController(false);
    }

    /* JADX INFO: renamed from: com.cooingdv.rcufo.fragment.DeviceBLFragment$3 */
    class C30653 implements OnSocketListener {
        C30653() {
        }

        @Override // com.cooingdv.rcufo.interfaces.OnSocketListener
        public void onConnected() {
            DeviceBLFragment.this.numPhoto = 0;
            DeviceBLFragment.this.numVideo = 0;
        }

        @Override // com.cooingdv.rcufo.interfaces.OnSocketListener
        public void onVideo(byte[] bArr) {
            if (DeviceBLFragment.this.isSupport) {
                if (DeviceBLFragment.this.noCardTaking) {
                    DeviceBLFragment.this.noCardTaking = false;
                    if (!TextUtils.isEmpty(DeviceBLFragment.this.savePhotoPath) && !TextUtils.isEmpty(DeviceBLFragment.this.savePhotoName)) {
                        DeviceBLFragment.this.mjpegThread.savePicture(DeviceBLFragment.this.savePhotoPath + File.separator + DeviceBLFragment.this.savePhotoName);
                    }
                }
                if (DeviceBLFragment.this.mjpegView.getVisibility() != 0) {
                    DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda8
                        @Override // java.lang.Runnable
                        public final void run() {
                            this.f$0.m35394lambda$onVideo$0$comcooingdvrcufofragmentDeviceBLFragment$3();
                        }
                    });
                }
                if (DeviceBLFragment.this.isVarMode && DeviceBLFragment.this.mjpegView2.getVisibility() != 0) {
                    DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda9
                        @Override // java.lang.Runnable
                        public final void run() {
                            this.f$0.m35395lambda$onVideo$1$comcooingdvrcufofragmentDeviceBLFragment$3();
                        }
                    });
                }
                if (DeviceBLFragment.this.mjpegThread != null) {
                    DeviceBLFragment.this.mjpegThread.drawBitmap(bArr);
                }
                if (DeviceBLFragment.this.mFlyController.isGestureMode()) {
                    DeviceBLFragment.this.mVideoData = bArr;
                    DeviceBLFragment.this.gestureRecognitionTimer();
                }
            }
        }

        /* JADX INFO: renamed from: lambda$onVideo$0$com-cooingdv-rcufo-fragment-DeviceBLFragment$3, reason: not valid java name */
        /* synthetic */ void m35394lambda$onVideo$0$comcooingdvrcufofragmentDeviceBLFragment$3() {
            DeviceBLFragment.this.mjpegView.setVisibility(0);
            DeviceBLFragment.this.ivBg.setVisibility(8);
        }

        /* JADX INFO: renamed from: lambda$onVideo$1$com-cooingdv-rcufo-fragment-DeviceBLFragment$3, reason: not valid java name */
        /* synthetic */ void m35395lambda$onVideo$1$comcooingdvrcufofragmentDeviceBLFragment$3() {
            DeviceBLFragment.this.mjpegView2.setVisibility(0);
            DeviceBLFragment.this.ivBg2.setVisibility(8);
        }

        @Override // com.cooingdv.rcufo.interfaces.OnSocketListener
        public void onReceiver(byte[] bArr) {
            if (bArr.length >= 1) {
                byte b = bArr[0];
                if (b != 102) {
                    DeviceBLFragment.this.setResolution(b);
                }
                if (WifiIdUtils.isGL(bArr[0]) && DeviceBLFragment.this.scaleViewLayout1.getVisibility() == 0) {
                    DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.3.1
                        @Override // java.lang.Runnable
                        public void run() {
                            DeviceBLFragment.this.scaleViewLayout1.setVisibility(8);
                            DeviceBLFragment.this.scaleViewLayout2.setVisibility(8);
                            DeviceBLFragment.this.scaleViewLayout3.setVisibility(8);
                            if (DeviceBLFragment.this.mFlyController.isFixedHeightMode()) {
                                return;
                            }
                            DeviceBLFragment.this.mFlyController.setFixedHeightMode(!DeviceBLFragment.this.mFlyController.isFixedHeightMode());
                            if (DeviceBLFragment.this.mFlyController.isFixedHeightMode()) {
                                DeviceBLFragment.this.rvVertical.setFixHeight(true);
                                DeviceBLFragment.this.adapter.setFixedHeightMode(true);
                                DeviceBLFragment.this.adapter.notifyDataSetChanged();
                                DeviceBLFragment.this.updateFixHeightUI(true);
                                PreferencesHelper.putBooleanValue(DeviceBLFragment.this.getActivity(), IConstants.FIX_HEIGHT_SHARE_KEY, true);
                                FlyController flyController = DeviceBLFragment.this.mFlyController;
                                Objects.requireNonNull(DeviceBLFragment.this.mFlyController);
                                flyController.setControlAccelerator(128);
                            }
                        }
                    });
                }
            }
            if (SocketClient.getInstance().getDeviceType() == 2) {
                if (bArr[0] != 102) {
                    if (DeviceBLFragment.this.isTakingControl) {
                        DeviceBLFragment.this.isTakingControl = false;
                        return;
                    }
                    return;
                }
                if (bArr[1] == 0) {
                    int iIntValue = Integer.valueOf(BufChangeHex.byteToHex(bArr[2]), 16).intValue();
                    int iIntValue2 = Integer.valueOf(BufChangeHex.byteToHex(bArr[9]), 16).intValue();
                    if (iIntValue != 1 || iIntValue2 != 1) {
                        if (DeviceBLFragment.this.isTakingControl) {
                            DeviceBLFragment.this.isTakingControl = false;
                        }
                    } else if (!DeviceBLFragment.this.isTakingControl) {
                        DeviceBLFragment.this.isTakingControl = true;
                        DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda0
                            @Override // java.lang.Runnable
                            public final void run() {
                                this.f$0.m13256x96b166d7();
                            }
                        });
                    }
                    if (iIntValue == 2 && iIntValue2 == 2) {
                        DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda1
                            @Override // java.lang.Runnable
                            public final void run() {
                                this.f$0.m13257xd07c08b6();
                            }
                        });
                        return;
                    }
                    return;
                }
                if (bArr.length == 10 || bArr.length == 15) {
                    int iIntValue3 = Integer.valueOf(BufChangeHex.byteToHex(bArr[4]), 16).intValue();
                    if (iIntValue3 == 2) {
                        if (!DeviceBLFragment.this.isTakingControl) {
                            DeviceBLFragment.this.isTakingControl = true;
                            DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda2
                                @Override // java.lang.Runnable
                                public final void run() {
                                    this.f$0.m13258xa46aa95();
                                }
                            });
                        }
                    } else if (DeviceBLFragment.this.isTakingControl) {
                        DeviceBLFragment.this.isTakingControl = false;
                    }
                    if (iIntValue3 == 4) {
                        DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda3
                            @Override // java.lang.Runnable
                            public final void run() {
                                this.f$0.m13259x44114c74();
                            }
                        });
                        return;
                    }
                    return;
                }
                return;
            }
            if (bArr.length > 4) {
                byte b2 = bArr[2];
                if (b2 == 77) {
                    int i = Integer.parseInt(BufChangeHex.byteToHex(bArr[3]), 16);
                    if (i > DeviceBLFragment.this.numPhoto || (DeviceBLFragment.this.numPhoto == 255 && i < DeviceBLFragment.this.numPhoto)) {
                        DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda4
                            @Override // java.lang.Runnable
                            public final void run() {
                                this.f$0.m13260x7ddbee53();
                            }
                        });
                        DeviceBLFragment.this.numPhoto = i;
                        SocketClient.getInstance().debugSend(new byte[]{9, 1});
                        return;
                    }
                    return;
                }
                if (b2 == 88) {
                    int i2 = Integer.parseInt(BufChangeHex.byteToHex(bArr[4]), 16);
                    if (i2 > DeviceBLFragment.this.numVideo || (DeviceBLFragment.this.numVideo == 255 && i2 < DeviceBLFragment.this.numVideo)) {
                        DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda5
                            @Override // java.lang.Runnable
                            public final void run() {
                                this.f$0.m13261xb7a69032();
                            }
                        });
                        DeviceBLFragment.this.numVideo = i2;
                        SocketClient.getInstance().debugSend(new byte[]{9, 2});
                        return;
                    }
                    return;
                }
                return;
            }
            if (bArr.length >= 3) {
                byte b3 = bArr[2];
                if (b3 == 77) {
                    DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda6
                        @Override // java.lang.Runnable
                        public final void run() {
                            this.f$0.m13262xf1713211();
                        }
                    });
                } else if (b3 == 88) {
                    DeviceBLFragment.this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment$3$$ExternalSyntheticLambda7
                        @Override // java.lang.Runnable
                        public final void run() {
                            this.f$0.m13263x2b3bd3f0();
                        }
                    });
                }
            }
        }

        /* JADX INFO: renamed from: lambda$onReceiver$2$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13256x96b166d7() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(1), 1, DeviceBLFragment.this.topListView.getItemIdAtPosition(1));
        }

        /* JADX INFO: renamed from: lambda$onReceiver$3$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13257xd07c08b6() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(2), 2, DeviceBLFragment.this.topListView.getItemIdAtPosition(2));
        }

        /* JADX INFO: renamed from: lambda$onReceiver$4$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13258xa46aa95() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(1), 1, DeviceBLFragment.this.topListView.getItemIdAtPosition(1));
        }

        /* JADX INFO: renamed from: lambda$onReceiver$5$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13259x44114c74() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(2), 2, DeviceBLFragment.this.topListView.getItemIdAtPosition(2));
        }

        /* JADX INFO: renamed from: lambda$onReceiver$6$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13260x7ddbee53() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(1), 1, DeviceBLFragment.this.topListView.getItemIdAtPosition(1));
        }

        /* JADX INFO: renamed from: lambda$onReceiver$7$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13261xb7a69032() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(2), 2, DeviceBLFragment.this.topListView.getItemIdAtPosition(2));
        }

        /* JADX INFO: renamed from: lambda$onReceiver$8$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13262xf1713211() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(1), 1, DeviceBLFragment.this.topListView.getItemIdAtPosition(1));
        }

        /* JADX INFO: renamed from: lambda$onReceiver$9$com-cooingdv-rcufo-fragment-DeviceBLFragment$3 */
        /* synthetic */ void m13263x2b3bd3f0() {
            DeviceBLFragment.this.topListView.performItemClick(DeviceBLFragment.this.topListView.getChildAt(2), 2, DeviceBLFragment.this.topListView.getItemIdAtPosition(2));
        }
    }

    private void showRecordingUI() {
        if (getActivity() != null) {
            if (this.myTimer == null) {
                MyTimer myTimer = new MyTimer(this.mHandler);
                this.myTimer = myTimer;
                myTimer.setTimer(this.deviceVideoTime);
                this.myTimer.start();
            }
            this.tvPortraitTime.setVisibility(0);
        }
    }

    private void HideRecordingUI() {
        if (getActivity() != null) {
            MyTimer myTimer = this.myTimer;
            if (myTimer != null) {
                myTimer.stopTimer();
                this.deviceVideoTime = 0;
                this.myTimer = null;
            }
            this.tvPortraitTime.setText("");
            this.tvPortraitTime.setVisibility(8);
        }
    }

    @Override // androidx.fragment.app.Fragment
    public void onPause() {
        super.onPause();
        if (this.noCardRecording) {
            stopNoCardRecording();
        }
        ViewPropertyAnimator viewPropertyAnimator = this.animator;
        if (viewPropertyAnimator != null) {
            viewPropertyAnimator.cancel();
        }
    }

    private void startNoCardRecording() {
        if (this.mjpegView.getVisibility() != 0) {
            showShortToast(C3033R.string.connect_device_tip);
            return;
        }
        initRecordStreamer(20, this.mjpegThread.getContrastCompressWidth(), this.mjpegThread.getContrastCompressHeight());
        VideoModel videoModel = this.videoModel;
        if (videoModel == null || videoModel.isRecording()) {
            return;
        }
        if ("mounted".equals(Environment.getExternalStorageState())) {
            long sdCardFreeBytes = StorageUtil.getSdCardFreeBytes();
            if (sdCardFreeBytes <= IConstants.MIN_STORAGE_SPACE) {
                showLongToast(C3033R.string.phone_space_inefficient);
                return;
            }
            if (sdCardFreeBytes < ((long) this.noCardRecordMax) * 31457280) {
                this.noCardRecordMax = (int) (((sdCardFreeBytes / 5) * 4) / 31457280);
            }
            showRecordingUI();
            Dbug.m13285e(this.TAG, "startNoCardRecording startRecording=");
            this.videoModel.startRecorder();
            this.mjpegThread.setModel(this.videoModel);
            this.noCardRecording = true;
            this.adapter.setRecordVideo(true);
            this.adapter.notifyDataSetChanged();
            this.btnPortraitVideo.setImageResource(C3033R.drawable.drawable_video_yellow);
            if (this.mFlyController.isMusicMode()) {
                int i = this.musicType;
                if (i == 1 || i == 2) {
                    this.musicUtils.setComposeMusic(this.assetManager, i, this.musicName);
                    return;
                } else {
                    if (i == 3) {
                        this.musicUtils.setComposeMusic(this.musicPath);
                        return;
                    }
                    return;
                }
            }
            return;
        }
        showLongToast(C3033R.string.not_found_phone_sdcard);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void stopNoCardRecording() {
        if (this.videoModel != null) {
            TopListViewAdapter topListViewAdapter = this.adapter;
            if (topListViewAdapter != null) {
                topListViewAdapter.setRecordVideo(false);
                this.adapter.notifyDataSetChanged();
            }
            this.btnPortraitVideo.setImageResource(C3033R.drawable.drawable_video);
            VideoModel videoModel = this.videoModel;
            if (videoModel != null && videoModel.isRecording()) {
                this.videoModel.stopRecorder();
            }
            this.noCardRecording = false;
        }
        HideRecordingUI();
    }

    private void startNoCardTaking() {
        if (this.mjpegView.getVisibility() != 0) {
            showShortToast(C3033R.string.connect_device_tip);
            return;
        }
        if (!"mounted".equals(Environment.getExternalStorageState())) {
            showLongToast(C3033R.string.not_found_phone_sdcard);
            return;
        }
        if (StorageUtil.getSdCardFreeBytes() <= IConstants.MIN_STORAGE_SPACE) {
            showLongToast(C3033R.string.phone_space_inefficient);
            return;
        }
        String photoPath = AppUtils.getPhotoPath(getActivity());
        if (TextUtils.isEmpty(photoPath)) {
            Dbug.m13285e(this.TAG, "Record dir is null");
            return;
        }
        File file = new File(photoPath);
        if (!file.exists() && !file.mkdir()) {
            throw new IllegalAccessError("Create " + photoPath + " failure.");
        }
        this.savePhotoPath = photoPath;
        this.savePhotoName = "JPG_" + TimeFormater.formatYMD_HMS(System.currentTimeMillis()) + ".jpg";
        SoundUtils.shootSound(getActivity());
        this.noCardTaking = true;
    }

    private void openGesture() {
        FlyController flyController = this.mFlyController;
        if (flyController != null) {
            flyController.setGestureMode(!flyController.isGestureMode());
            if (this.mFlyController.isGestureMode()) {
                this.btnGesture.setImageResource(C3033R.drawable.drawable_gesture_recognition_open);
                this.btnPortraitGesture.setImageResource(C3033R.drawable.drawable_gesture_recognition_open);
                this.layoutVideoView.setVisibility(0);
                return;
            }
            this.btnGesture.setImageResource(C3033R.drawable.drawable_gesture_recognition_close);
            this.btnPortraitGesture.setImageResource(C3033R.drawable.drawable_gesture_recognition_close);
            this.layoutVideoView.setVisibility(8);
            this.mVideoData = null;
            Timer timer = this.gestureTimer;
            if (timer != null) {
                timer.cancel();
                this.gestureTimer = null;
            }
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void gestureRecognitionTimer() {
        if (this.gestureTimer == null) {
            Timer timer = new Timer();
            this.gestureTimer = timer;
            timer.schedule(new TimerTask() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.4
                @Override // java.util.TimerTask, java.lang.Runnable
                public void run() {
                    if (DeviceBLFragment.this.mFlyController.isGestureMode()) {
                        String documentsPath = AppUtils.getDocumentsPath(DeviceBLFragment.this.getActivity());
                        if (DeviceBLFragment.this.isRecognition || DeviceBLFragment.this.mVideoData == null || DeviceBLFragment.this.mVideoData.length <= 0 || !BufChangeHex.byte2File(DeviceBLFragment.this.mVideoData, documentsPath, IConstants.GESTRUE_FILE_NAME)) {
                            return;
                        }
                        if (DeviceBLFragment.this.mjpegThread.getTurnBitmap()) {
                            String str = documentsPath + File.separator + IConstants.GESTRUE_FILE_NAME;
                            BitmapUtil.saveBitmap(str, BitmapUtil.rotateBitmap(BitmapUtil.getImage(str, false), -180.0f));
                        }
                        int[] iArrGestureRecognition = RecognitionUtils.gestureRecognition();
                        int i = (iArrGestureRecognition == null || iArrGestureRecognition.length <= 0) ? 0 : iArrGestureRecognition[0];
                        if (i == 2 || DeviceBLFragment.this.palmCount > 0) {
                            DeviceBLFragment.access$3708(DeviceBLFragment.this);
                        }
                        if (i == 1 || (i == 2 && DeviceBLFragment.this.palmCount > 1)) {
                            Message messageObtainMessage = DeviceBLFragment.this.mHandler.obtainMessage();
                            messageObtainMessage.what = DeviceBLFragment.MSG_GESTURE_TOAST;
                            messageObtainMessage.obj = iArrGestureRecognition;
                            DeviceBLFragment.this.mHandler.sendMessage(messageObtainMessage);
                            DeviceBLFragment.this.palmCount = 0;
                        }
                        if (DeviceBLFragment.this.palmCount > 2) {
                            DeviceBLFragment.this.palmCount = 0;
                        }
                        Dbug.m13285e(DeviceBLFragment.this.TAG, "gesture values = " + String.valueOf(i));
                    }
                }
            }, 1000L, 1000L);
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void gestureRecogFrame(int[] iArr) {
        ImageView imageView = new ImageView(getActivity());
        imageView.setImageResource(C3033R.mipmap.gesture_recognition_confirm);
        int width = this.layoutVideoView.getWidth();
        int height = this.layoutVideoView.getHeight();
        float contrastCompressWidth = (width * 1.0f) / this.mjpegThread.getContrastCompressWidth();
        float contrastCompressHeight = (height * 1.0f) / this.mjpegThread.getContrastCompressHeight();
        int i = iArr[1];
        int i2 = iArr[2];
        int i3 = iArr[3];
        int i4 = iArr[4];
        imageView.setX((int) (i * contrastCompressWidth));
        imageView.setY((int) (i2 * contrastCompressHeight));
        this.layoutVideoView.addView(imageView, (int) (i3 * contrastCompressWidth), (int) (i4 * contrastCompressHeight));
    }

    private void initRecordStreamer(int i, int i2, int i3) {
        String videoPath = AppUtils.getVideoPath(getActivity());
        if (TextUtils.isEmpty(videoPath)) {
            Dbug.m13285e(this.TAG, "Record dir is null");
            return;
        }
        File file = new File(videoPath);
        if (!file.exists() && !file.mkdir()) {
            Dbug.m13285e(this.TAG, "mkdir Record dir failed!");
            return;
        }
        Dbug.m13286i(this.TAG, "initRecordStreamer dirPath = " + videoPath);
        if (this.videoModel != null) {
            this.mjpegThread.setFps(i);
            int i4 = this.fakeResolutionType;
            if (i4 == 1) {
                i2 = 640;
                i3 = DtbConstants.DEFAULT_PLAYER_HEIGHT;
            } else if (i4 != 3) {
                if (i4 != 4) {
                    i2 = (i4 == 5 || i4 == 6) ? 2048 : 1920;
                }
                i3 = 1080;
            } else {
                i2 = 1280;
                i3 = 720;
            }
            if (this.mjpegThread.isPortrait()) {
                this.videoModel.init(i3, i2, i);
            } else {
                this.videoModel.init(i2, i3, i);
            }
            Dbug.m13286i(this.TAG, "video model init : width = " + i2 + ", height = " + i3);
        }
    }

    public void initFixHeight() {
        boolean z = PreferencesHelper.getSharedPreferences(getActivity()).getBoolean(IConstants.FIX_HEIGHT_SHARE_KEY, true);
        FlyController flyController = this.mFlyController;
        if (flyController != null) {
            flyController.setFixedHeightMode(z);
            if (z) {
                this.rvVertical.setFixHeight(true);
                updateFixHeightUI(true);
                FlyController flyController2 = this.mFlyController;
                Objects.requireNonNull(flyController2);
                flyController2.setControlAccelerator(128);
                this.adapter.setFixedHeightMode(true);
                this.adapter.notifyDataSetChanged();
                return;
            }
            this.rvVertical.setFixHeight(false);
            updateFixHeightUI(false);
            this.mFlyController.setControlAccelerator(0);
            this.adapter.setFixedHeightMode(false);
            this.adapter.notifyDataSetChanged();
        }
    }

    public void initScreen() {
        boolean z = PreferencesHelper.getSharedPreferences(getActivity()).getBoolean(IConstants.SCREEN_DIRECTION_SHARE_KEY, false);
        MjpegThread mjpegThread = this.mjpegThread;
        if (mjpegThread != null) {
            mjpegThread.setTurnBitmap(z);
        }
        this.adapter.setTurn180(z);
        this.adapter.notifyDataSetChanged();
        if (this.isVarMode) {
            this.ivBg2.setVisibility(0);
        } else {
            this.mjpegView2.setVisibility(8);
            this.ivBg2.setVisibility(8);
        }
        try {
            if (this.mSensorHelper == null && Settings.System.getInt(getActivity().getContentResolver(), "accelerometer_rotation") == 1) {
                ScreenSensorHelper screenSensorHelper = new ScreenSensorHelper(getActivity());
                this.mSensorHelper = screenSensorHelper;
                screenSensorHelper.enable();
            }
            saveGestureXml();
        } catch (Settings.SettingNotFoundException e) {
            throw new RuntimeException(e);
        }
    }

    private void saveGestureXml() {
        new Thread(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.5
            @Override // java.lang.Runnable
            public void run() {
                StorageUtil.copyFilesFromRaw(DeviceBLFragment.this.getActivity(), C3033R.raw.fist, "fist.xml", AppUtils.getDocumentsPath(DeviceBLFragment.this.getActivity()));
                StorageUtil.copyFilesFromRaw(DeviceBLFragment.this.getActivity(), C3033R.raw.rpalm, "rpalm.xml", AppUtils.getDocumentsPath(DeviceBLFragment.this.getActivity()));
            }
        }).start();
    }

    public void initStatus() {
        initScreen();
        initFixHeight();
    }

    @Override // com.cooingdv.rcufo.libs.TrackView.OnTrackListener
    public void onTrackStart(List<Point> list, List<Point> list2) {
        ImageView imageView = this.air;
        if (imageView != null) {
            imageView.setVisibility(8);
            this.air = null;
        }
        if (list.size() > 2) {
            ImageView imageView2 = new ImageView(getActivity());
            this.air = imageView2;
            imageView2.setImageResource(C3033R.mipmap.aircraft);
            this.airWidth = this.air.getDrawable().getIntrinsicWidth();
            this.airHeight = this.air.getDrawable().getIntrinsicHeight();
            this.air.setX(list.get(0).x - (this.airWidth / 2));
            this.air.setY(list.get(0).y - (this.airHeight / 2));
            this.layoutControlRightDraw.addView(this.air);
            this.animator = this.air.animate();
            startTrackAnimation(list, list2);
        }
    }

    @Override // com.cooingdv.rcufo.libs.TrackView.OnTrackListener
    public void onTrackStop() {
        ViewPropertyAnimator viewPropertyAnimator = this.animator;
        if (viewPropertyAnimator != null) {
            viewPropertyAnimator.cancel();
        }
    }

    private void startTrackAnimation(List<Point> list, List<Point> list2) {
        this.animator.translationX(list.get(0).x - (this.airWidth / 2)).translationY(list.get(0).y - (this.airHeight / 2)).setInterpolator(new LinearInterpolator()).setDuration(500L).setListener(new TrackAnimationListener(list, list2, this.air, this.trackView, this.airWidth, this.airHeight, this));
    }

    @Override // com.cooingdv.rcufo.tools.TrackAnimationListener.AnimatorTrackListener
    public void trackFly(float f, float f2) {
        int i;
        float halfLen = getHalfLen();
        int i2 = (int) ((f / 214.0f) * halfLen);
        int i3 = (int) ((f2 / 214.0f) * halfLen);
        int i4 = this.currPower;
        if (i4 == 4) {
            int i5 = i2 + (this.horizontalCenterCurrentValue * 2);
            Objects.requireNonNull(this.mFlyController);
            i2 = i5 + 128;
            i = i3 + (this.verticalCurrentValue * 2);
            Objects.requireNonNull(this.mFlyController);
        } else if (i4 == 9) {
            int i6 = i2 + (this.horizontalCenterCurrentValue * 3);
            Objects.requireNonNull(this.mFlyController);
            i2 = i6 + 128;
            i = i3 + (this.verticalCurrentValue * 3);
            Objects.requireNonNull(this.mFlyController);
        } else {
            if (i4 == 14) {
                int i7 = i2 + (this.horizontalCenterCurrentValue * 4);
                Objects.requireNonNull(this.mFlyController);
                i2 = i7 + 128;
                i = i3 + (this.verticalCurrentValue * 4);
                Objects.requireNonNull(this.mFlyController);
            }
            this.mFlyController.setControlByte1(i2);
            this.mFlyController.setControlByte2(i3);
        }
        i3 = i + 128;
        this.mFlyController.setControlByte1(i2);
        this.mFlyController.setControlByte2(i3);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void setResolution(int i) {
        this.isSupport = WifiIdUtils.isPasswordWifi(i) ? SocketClient.getInstance().isPasswordCorrect() : WifiIdUtils.isSupport(i);
        this.mApplication.setDeviceUUID(String.valueOf(i));
        int fakeResolution = WifiIdUtils.getFakeResolution(i);
        this.fakeResolutionType = fakeResolution;
        if ((fakeResolution == 5 || fakeResolution == 6) && AppUtils.isNotSupport4K()) {
            this.fakeResolutionType = 4;
        }
        MjpegThread mjpegThread = this.mjpegThread;
        if (mjpegThread != null) {
            mjpegThread.setFakeResolution(this.fakeResolutionType);
        }
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicComposeListener
    public void onComposeStart() {
        this.isMusicComposing = true;
        this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.6
            @Override // java.lang.Runnable
            public void run() {
                DeviceBLFragment.this.progressBarMusic.setVisibility(0);
            }
        });
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicComposeListener
    public void onComposeFinish() {
        this.isMusicComposing = false;
        this.mHandler.post(new Runnable() { // from class: com.cooingdv.rcufo.fragment.DeviceBLFragment.7
            @Override // java.lang.Runnable
            public void run() {
                DeviceBLFragment.this.progressBarMusic.setVisibility(8);
            }
        });
    }

    @Override // android.widget.SeekBar.OnSeekBarChangeListener
    public void onProgressChanged(SeekBar seekBar, int i, boolean z) {
        if (i <= 1) {
            this.tvScale.setVisibility(4);
            this.lastScaleY = 0.0f;
            this.lastScaleX = 0.0f;
        } else {
            this.tvScale.setVisibility(0);
            this.tvScale.setText(String.valueOf(i) + "X");
        }
        if (i == 50) {
            i = 49;
        }
        this.mjpegThread.setFocusScale(i);
    }

    @Override // android.view.View.OnTouchListener
    public boolean onTouch(View view, MotionEvent motionEvent) {
        if (view.getId() == C3033R.id.device_video_view) {
            int action = motionEvent.getAction();
            if (action == 0) {
                this.startX = motionEvent.getX();
                this.startY = motionEvent.getY();
            } else if (action == 1) {
                this.lastScaleX += motionEvent.getX() - this.startX;
                this.lastScaleY += motionEvent.getY() - this.startY;
            } else if (action == 2) {
                this.mjpegThread.setFocusMove((motionEvent.getX() - this.startX) + this.lastScaleX, (motionEvent.getY() - this.startY) + this.lastScaleY);
            }
        }
        return true;
    }

    @Override // com.cooingdv.rcufo.libs.RockerView.OnShakeListener
    public void onFinish(RockerView rockerView) {
        if (rockerView == this.rvVertical && this.ivLeftBgRocker.getVisibility() == 0) {
            this.ivLeftBgRocker.setVisibility(8);
        }
        if (rockerView == this.rvHorizontal && this.ivRightBgRocker.getVisibility() == 0) {
            this.ivRightBgRocker.setVisibility(8);
        }
    }

    @Override // com.cooingdv.rcufo.libs.RockerView.OnAngleChangeListener
    public void angle(RockerView rockerView, double d) {
        if (rockerView == this.rvVertical) {
            this.ivLeftBgRocker.setRotation(((float) d) + 90.0f);
        }
        if (rockerView == this.rvHorizontal) {
            this.ivRightBgRocker.setRotation(((float) d) + 90.0f);
        }
    }

    @Override // androidx.fragment.app.Fragment, android.content.ComponentCallbacks
    public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        if (getActivity() != null) {
            if (getActivity().getRequestedOrientation() == 1) {
                ScreenSensorHelper screenSensorHelper = this.mSensorHelper;
                if (screenSensorHelper != null) {
                    screenSensorHelper.setPortLock(true);
                    this.mSensorHelper.setLandLock(false);
                }
                if (this.mFlyController.isControlMode()) {
                    updateModeUI();
                }
                if (this.isVarMode) {
                    this.isVarMode = false;
                    this.btnVRMode.setImageResource(C3033R.drawable.drawable_vr_yellow);
                    this.mjpegView2.setVisibility(8);
                    this.ivBg2.setVisibility(8);
                    this.mjpegView.setScaleType(ImageView.ScaleType.FIT_XY);
                    if (this.mFlyController.isControlMode()) {
                        this.LayoutControlMode.setVisibility(0);
                    }
                }
                if (this.layoutScaleSeek.getVisibility() == 0) {
                    this.layoutScaleSeek.setVisibility(8);
                    this.btnScale.setImageResource(C3033R.drawable.drawable_scale);
                }
                if (this.mVerticalSeekBar.getProgress() > 1) {
                    this.mVerticalSeekBar.setProgress(0);
                    this.tvScale.setVisibility(4);
                    this.lastScaleY = 0.0f;
                    this.lastScaleX = 0.0f;
                }
                this.topListView.setVisibility(8);
                if (this.adapter.isMenuOpen()) {
                    this.layoutDownMenu.setVisibility(8);
                    this.adapter.setMenuOpen(false);
                    this.adapter.notifyDataSetChanged();
                }
                this.layoutPortrait.setVisibility(0);
                MjpegThread mjpegThread = this.mjpegThread;
                if (mjpegThread != null) {
                    mjpegThread.setPortrait(true);
                    return;
                }
                return;
            }
            ScreenSensorHelper screenSensorHelper2 = this.mSensorHelper;
            if (screenSensorHelper2 != null) {
                screenSensorHelper2.setLandLock(true);
                this.mSensorHelper.setPortLock(false);
            }
            this.layoutPortrait.setVisibility(8);
            this.topListView.setVisibility(0);
            MjpegThread mjpegThread2 = this.mjpegThread;
            if (mjpegThread2 != null) {
                mjpegThread2.setPortrait(false);
            }
        }
    }
}
