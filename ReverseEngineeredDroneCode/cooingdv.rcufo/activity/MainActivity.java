package com.cooingdv.rcufo.activity;

import android.content.Intent;
import android.media.AudioManager;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.View;
import android.widget.FrameLayout;
import androidx.core.view.OnApplyWindowInsetsListener;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.fragment.app.Fragment;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.fragment.MenuFragment;
import com.cooingdv.rcufo.socket.SocketClient;
import com.cooingdv.rcufo.tools.GoogleMobileAdsConsentManager;
import com.cooingdv.rcufo.tools.IActions;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.Dbug;
import com.cooingdv.rcufo.utils.LocalUtil;
import com.google.android.ump.FormError;
import java.util.Locale;
import tv.danmaku.ijk.media.widget.IjkVideoView;

/* JADX INFO: loaded from: classes2.dex */
public class MainActivity extends BaseActivity {
    private AudioManager audioManager;
    private long mBackPressedTimes;
    private SocketClient mSocketClient;
    private IjkVideoView mVideoView;

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setContentView(C3033R.layout.activity_main);
        getWindow().addFlags(128);
        this.mVideoView = (IjkVideoView) findViewById(C3033R.id.main_tx_video_view);
        this.audioManager = (AudioManager) getSystemService("audio");
        initUI();
        SocketClient socketClient = SocketClient.getInstance();
        this.mSocketClient = socketClient;
        socketClient.initVideoView(this.mVideoView, this);
        this.mSocketClient.start();
        loadAndShowConsentFormIfRequired();
    }

    private void stopMusic() {
        AudioManager audioManager = this.audioManager;
        if (audioManager == null || !audioManager.isMusicActive()) {
            return;
        }
        this.audioManager.requestAudioFocus(null, 3, 2);
    }

    @Override // androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onStart() {
        super.onStart();
        setLanguage();
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onResume() {
        super.onResume();
        stopMusic();
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onDestroy() {
        Dbug.m13285e(this.TAG, "MainActivity is onDestroy");
        release();
        super.onDestroy();
    }

    @Override // androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, android.app.Activity
    protected void onNewIntent(Intent intent) {
        Locale language = AppUtils.getLanguage(PreferencesHelper.getSharedPreferences(getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(this)));
        if (language != null) {
            AppUtils.setLanguage(getApplicationContext(), language);
        }
        super.onNewIntent(intent);
        setIntent(intent);
        initUI();
    }

    @Override // androidx.activity.ComponentActivity, android.app.Activity
    public void onBackPressed() {
        if (!(((BaseFragment) getSupportFragmentManager().findFragmentById(C3033R.id.main_frame_layout)) instanceof MenuFragment)) {
            super.onBackPressed();
        } else if (this.mBackPressedTimes + 2000 > System.currentTimeMillis()) {
            sendBroadcast(new Intent(IActions.ACTION_QUIT_APP));
        } else {
            showToastShort(C3033R.string.double_tap_to_exit);
            this.mBackPressedTimes = System.currentTimeMillis();
        }
    }

    private void initUI() {
        String str;
        ViewCompat.setOnApplyWindowInsetsListener((FrameLayout) findViewById(C3033R.id.main_frame_layout), new OnApplyWindowInsetsListener() { // from class: com.cooingdv.rcufo.activity.MainActivity$$ExternalSyntheticLambda0
            @Override // androidx.core.view.OnApplyWindowInsetsListener
            public final WindowInsetsCompat onApplyWindowInsets(View view, WindowInsetsCompat windowInsetsCompat) {
                return MainActivity.lambda$initUI$0(view, windowInsetsCompat);
            }
        });
        Fragment menuFragment = (BaseFragment) getSupportFragmentManager().findFragmentById(C3033R.id.main_frame_layout);
        if (menuFragment == null) {
            menuFragment = new MenuFragment();
            str = IConstants.FRAGMENT_TAG_MENU;
        } else {
            str = null;
        }
        if (!TextUtils.isEmpty(str)) {
            changeFragment(C3033R.id.main_frame_layout, menuFragment, str, true);
        } else {
            changeFragment(C3033R.id.main_frame_layout, menuFragment);
        }
    }

    static /* synthetic */ WindowInsetsCompat lambda$initUI$0(View view, WindowInsetsCompat windowInsetsCompat) {
        view.setPadding(0, 0, windowInsetsCompat.getInsets(WindowInsetsCompat.Type.navigationBars()).right, 0);
        return windowInsetsCompat;
    }

    private void loadAndShowConsentFormIfRequired() {
        final GoogleMobileAdsConsentManager googleMobileAdsConsentManager = GoogleMobileAdsConsentManager.getInstance(this);
        googleMobileAdsConsentManager.gatherConsent(this, new GoogleMobileAdsConsentManager.OnConsentGatheringCompleteListener() { // from class: com.cooingdv.rcufo.activity.MainActivity.1
            @Override // com.cooingdv.rcufo.tools.GoogleMobileAdsConsentManager.OnConsentGatheringCompleteListener
            public void consentGatheringComplete(FormError formError) {
                if (googleMobileAdsConsentManager.canRequestAds()) {
                    Dbug.m13285e("UNAD_SDK", "通过");
                }
            }
        });
    }
}
