package com.cooingdv.rcufo.activity;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.MainApplication;
import com.cooingdv.rcufo.utils.Dbug;
import com.unad.sdk.UNADSplash;
import com.unad.sdk.dto.AdError;

/* JADX INFO: loaded from: classes2.dex */
public class SplashActivity extends Activity {
    public boolean canJump = false;

    @Override // android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setContentView(C3033R.layout.activity_splash);
        MainApplication mainApplication = (MainApplication) getApplication();
        mainApplication.setRun(false);
        if (mainApplication.isFirstStartAPP()) {
            return;
        }
        loadAd();
    }

    public void loadAd() {
        UNADSplash uNADSplash = new UNADSplash(getApplication());
        uNADSplash.setSkipButtonType(UNADSplash.SKIPTYPE.CLICK);
        uNADSplash.setAdUnitId("Adgo-unit-8982251961");
        uNADSplash.setAdViewListener(new UNADSplash.AdViewListener() { // from class: com.cooingdv.rcufo.activity.SplashActivity.1
            @Override // com.unad.sdk.UNADSplash.AdViewListener
            public void onAdClicked() {
            }

            @Override // com.unad.sdk.UNADSplash.AdViewListener
            public void onAdLoaded() {
                SplashActivity.this.canJump = true;
                Dbug.m13285e("UNAD_SDK", "UI  :onAdViewLoaded");
            }

            @Override // com.unad.sdk.UNADSplash.AdViewListener
            public void onAdFailed(AdError adError) {
                Dbug.m13285e("UNAD_SDK", "UI  :onAdViewFailed" + adError.getMessage());
                SplashActivity.this.startMain();
            }

            @Override // com.unad.sdk.UNADSplash.AdViewListener
            public void onAdClose() {
                Dbug.m13285e("UNAD_SDK", "UI  :onAdViewClose");
                SplashActivity.this.startMain();
            }

            @Override // com.unad.sdk.UNADSplash.AdViewListener
            public void onAdOpen() {
                Dbug.m13285e("UNAD_SDK", "UI  :onAdOpen");
            }
        });
        uNADSplash.setLogoPicture(C3033R.mipmap.splash_bg);
        uNADSplash.setDurationTime(10);
        uNADSplash.setAppName(getString(C3033R.string.app_name));
        uNADSplash.setLogoPicture(C3033R.mipmap.ic_logo);
        uNADSplash.setIntervals(1800);
        uNADSplash.setTimeoutTime(8);
        uNADSplash.loadAd(this);
    }

    @Override // android.app.Activity
    protected void onPause() {
        super.onPause();
        this.canJump = false;
    }

    @Override // android.app.Activity
    protected void onResume() {
        super.onResume();
        if (this.canJump) {
            startMain();
        }
        this.canJump = true;
    }

    public void startMain() {
        if (this.canJump) {
            MainApplication mainApplication = (MainApplication) getApplication();
            if (mainApplication.isRun) {
                return;
            }
            startActivity(new Intent(this, (Class<?>) MainActivity.class));
            finish();
            mainApplication.setRun(true);
            return;
        }
        this.canJump = true;
    }
}
