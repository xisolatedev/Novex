package com.cooingdv.rcufo.activity;

import android.content.Intent;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.View;
import android.widget.ImageView;
import android.widget.RelativeLayout;
import android.widget.TextView;
import androidx.core.view.OnApplyWindowInsetsListener;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.fragment.InstructionsFragment;
import com.cooingdv.rcufo.fragment.SettingsFragment;
import com.cooingdv.rcufo.tools.IConstants;

/* JADX INFO: loaded from: classes2.dex */
public class GenericActivity extends BaseActivity implements View.OnClickListener {
    private BaseFragment fragment = null;
    private View layoutTopBar;
    private TextView tvTopTitle;

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setContentView(C3033R.layout.activity_generic);
        getWindow().addFlags(128);
        RelativeLayout relativeLayout = (RelativeLayout) findViewById(C3033R.id.generic_layout);
        ImageView imageView = (ImageView) findViewById(C3033R.id.bar_generic_left_btn);
        TextView textView = (TextView) findViewById(C3033R.id.bar_generic_center_tv);
        this.tvTopTitle = textView;
        textView.setKeepScreenOn(true);
        imageView.setOnClickListener(this);
        this.layoutTopBar = findViewById(C3033R.id.generic_top_bar);
        ViewCompat.setOnApplyWindowInsetsListener(relativeLayout, new OnApplyWindowInsetsListener() { // from class: com.cooingdv.rcufo.activity.GenericActivity$$ExternalSyntheticLambda0
            @Override // androidx.core.view.OnApplyWindowInsetsListener
            public final WindowInsetsCompat onApplyWindowInsets(View view, WindowInsetsCompat windowInsetsCompat) {
                return GenericActivity.lambda$onCreate$0(view, windowInsetsCompat);
            }
        });
        Intent intent = getIntent();
        if (intent != null) {
            switchSubFragment(intent.getStringExtra(IConstants.KEY_FRAGMENT_TAG));
        }
    }

    static /* synthetic */ WindowInsetsCompat lambda$onCreate$0(View view, WindowInsetsCompat windowInsetsCompat) {
        view.setPadding(0, 0, windowInsetsCompat.getInsets(WindowInsetsCompat.Type.navigationBars()).right, 0);
        return windowInsetsCompat;
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onResume() {
        super.onResume();
    }

    @Override // com.cooingdv.rcufo.base.BaseActivity, androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onDestroy() {
        super.onDestroy();
    }

    @Override // androidx.activity.ComponentActivity, android.app.Activity
    public void onBackPressed() {
        finish();
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (view != null && view.getId() == C3033R.id.bar_generic_left_btn) {
            finish();
        }
    }

    private void switchSubFragment(String str) {
        String string;
        str.hashCode();
        if (str.equals(IConstants.FRAGMENT_TAG_SETTINGS)) {
            BaseFragment baseFragment = (BaseFragment) getSupportFragmentManager().findFragmentByTag(IConstants.FRAGMENT_TAG_SETTINGS);
            this.fragment = baseFragment;
            if (baseFragment == null) {
                this.fragment = new SettingsFragment();
            }
            string = getString(C3033R.string.item_system_settings);
        } else if (str.equals(IConstants.FRAGMENT_TAG_INSTRUCTIONS)) {
            BaseFragment baseFragment2 = (BaseFragment) getSupportFragmentManager().findFragmentByTag(IConstants.FRAGMENT_TAG_INSTRUCTIONS);
            this.fragment = baseFragment2;
            if (baseFragment2 == null) {
                this.fragment = new InstructionsFragment();
            }
            this.layoutTopBar.setVisibility(8);
            string = getString(C3033R.string.item_instructions);
        } else {
            string = null;
        }
        if (this.fragment == null || TextUtils.isEmpty(str)) {
            return;
        }
        changeFragment(C3033R.id.generic_frame_layout, this.fragment, str, true);
        if (TextUtils.isEmpty(string)) {
            return;
        }
        this.tvTopTitle.setText(string);
    }
}
