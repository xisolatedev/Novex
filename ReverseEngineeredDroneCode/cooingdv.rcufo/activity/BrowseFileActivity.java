package com.cooingdv.rcufo.activity;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.FrameLayout;
import androidx.core.view.OnApplyWindowInsetsListener;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.fragment.BrowseSelectFragment;
import com.cooingdv.rcufo.tools.IConstants;

/* JADX INFO: loaded from: classes2.dex */
public class BrowseFileActivity extends BaseActivity {
    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle bundle) {
        String stringExtra;
        super.onCreate(bundle);
        setContentView(C3033R.layout.activity_browse_file);
        getWindow().addFlags(128);
        ViewCompat.setOnApplyWindowInsetsListener((FrameLayout) findViewById(C3033R.id.browse_file_frame_layout), new OnApplyWindowInsetsListener() { // from class: com.cooingdv.rcufo.activity.BrowseFileActivity$$ExternalSyntheticLambda0
            @Override // androidx.core.view.OnApplyWindowInsetsListener
            public final WindowInsetsCompat onApplyWindowInsets(View view, WindowInsetsCompat windowInsetsCompat) {
                return BrowseFileActivity.lambda$onCreate$0(view, windowInsetsCompat);
            }
        });
        Intent intent = getIntent();
        if (intent == null) {
            stringExtra = IConstants.VIEW_FRONT;
        } else {
            stringExtra = intent.getStringExtra(IConstants.KEY_DIR_TYPE);
        }
        BaseFragment browseSelectFragment = (BaseFragment) getSupportFragmentManager().findFragmentByTag(IConstants.FRAGMENT_TAG_BROWSE_SELECT);
        if (browseSelectFragment == null) {
            browseSelectFragment = new BrowseSelectFragment();
        }
        Bundle bundle2 = new Bundle();
        bundle2.putString(IConstants.KEY_DIR_TYPE, stringExtra);
        browseSelectFragment.setBundle(bundle2);
        changeFragment(C3033R.id.browse_file_frame_layout, browseSelectFragment, IConstants.FRAGMENT_TAG_BROWSE_SELECT, true);
    }

    static /* synthetic */ WindowInsetsCompat lambda$onCreate$0(View view, WindowInsetsCompat windowInsetsCompat) {
        view.setPadding(0, 0, windowInsetsCompat.getInsets(WindowInsetsCompat.Type.navigationBars()).right, 0);
        return windowInsetsCompat;
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onResume() {
        super.onResume();
        setLanguage();
    }

    @Override // androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onStop() {
        super.onStop();
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onDestroy() {
        super.onDestroy();
        if (Thread.currentThread().isAlive()) {
            Thread.currentThread().interrupt();
        }
    }

    @Override // androidx.activity.ComponentActivity, android.app.Activity
    public void onBackPressed() {
        if (((BaseFragment) getSupportFragmentManager().findFragmentById(C3033R.id.browse_file_frame_layout)) instanceof BrowseSelectFragment) {
            finish();
        } else {
            super.onBackPressed();
        }
    }
}
