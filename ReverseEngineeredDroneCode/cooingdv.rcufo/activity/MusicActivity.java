package com.cooingdv.rcufo.activity;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.view.InputDeviceCompat;
import androidx.core.view.OnApplyWindowInsetsListener;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentActivity;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.fragment.LocalMusicFragment;
import com.cooingdv.rcufo.fragment.PopularMusicFragment;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.LocalUtil;
import com.cooingdv.rcufo.utils.MusicUtils;
import java.util.Locale;

/* JADX INFO: loaded from: classes2.dex */
public class MusicActivity extends FragmentActivity implements View.OnClickListener {
    private final String TAG = getClass().getSimpleName();
    private Fragment currentFragment;
    private MusicUtils mMusicUtils;
    TextView tvLocalMusic;
    TextView tvPopularMusicChinese;

    @Override // androidx.fragment.app.FragmentActivity, androidx.activity.ComponentActivity, androidx.core.app.ComponentActivity, android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        getWindow().setFlags(1024, 1024);
        setContentView(C3033R.layout.activity_music);
        getWindow().addFlags(128);
        initView();
    }

    private void initView() {
        LinearLayout linearLayout = (LinearLayout) findViewById(C3033R.id.music_layout);
        ImageView imageView = (ImageView) findViewById(C3033R.id.music_select_back_btn);
        Button button = (Button) findViewById(C3033R.id.music_select_turn_off_btn);
        this.tvPopularMusicChinese = (TextView) findViewById(C3033R.id.music_select_popular_chinese_music);
        this.tvLocalMusic = (TextView) findViewById(C3033R.id.music_select_local_music);
        imageView.setOnClickListener(this);
        button.setOnClickListener(this);
        this.tvPopularMusicChinese.setOnClickListener(this);
        this.tvLocalMusic.setOnClickListener(this);
        this.mMusicUtils = new MusicUtils(this);
        setLanguage();
        replaceFragment(IConstants.FRAGMENT_TAG_MUSIC_POPULAR_CHINESE);
        ViewCompat.setOnApplyWindowInsetsListener(linearLayout, new OnApplyWindowInsetsListener() { // from class: com.cooingdv.rcufo.activity.MusicActivity$$ExternalSyntheticLambda0
            @Override // androidx.core.view.OnApplyWindowInsetsListener
            public final WindowInsetsCompat onApplyWindowInsets(View view, WindowInsetsCompat windowInsetsCompat) {
                return MusicActivity.lambda$initView$0(view, windowInsetsCompat);
            }
        });
    }

    static /* synthetic */ WindowInsetsCompat lambda$initView$0(View view, WindowInsetsCompat windowInsetsCompat) {
        view.setPadding(0, 0, windowInsetsCompat.getInsets(WindowInsetsCompat.Type.navigationBars()).right, 0);
        return windowInsetsCompat;
    }

    private void replaceFragment(String str) {
        if (this.currentFragment != null) {
            getSupportFragmentManager().beginTransaction().hide(this.currentFragment).commit();
        }
        Fragment fragmentFindFragmentByTag = getSupportFragmentManager().findFragmentByTag(str);
        this.currentFragment = fragmentFindFragmentByTag;
        if (fragmentFindFragmentByTag == null) {
            str.hashCode();
            if (str.equals(IConstants.FRAGMENT_TAG_MUSIC_POPULAR_CHINESE)) {
                this.currentFragment = new PopularMusicFragment(this.mMusicUtils, str);
            } else if (str.equals(IConstants.FRAGMENT_TAG_MUSIC_LOCAL)) {
                this.currentFragment = new LocalMusicFragment(this.mMusicUtils);
            }
            getSupportFragmentManager().beginTransaction().add(C3033R.id.music_select_center_layout, this.currentFragment, str).commit();
            return;
        }
        getSupportFragmentManager().beginTransaction().show(this.currentFragment).commit();
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        switch (view.getId()) {
            case C3033R.id.music_select_back_btn /* 2131297169 */:
                finish();
                break;
            case C3033R.id.music_select_local_music /* 2131297172 */:
                ((TextView) view).setTextColor(InputDeviceCompat.SOURCE_ANY);
                this.tvPopularMusicChinese.setTextColor(-1);
                replaceFragment(IConstants.FRAGMENT_TAG_MUSIC_LOCAL);
                break;
            case C3033R.id.music_select_popular_chinese_music /* 2131297175 */:
                this.tvPopularMusicChinese.setTextColor(InputDeviceCompat.SOURCE_ANY);
                this.tvLocalMusic.setTextColor(-1);
                replaceFragment(IConstants.FRAGMENT_TAG_MUSIC_POPULAR_CHINESE);
                break;
            case C3033R.id.music_select_turn_off_btn /* 2131297180 */:
                Intent intent = new Intent();
                intent.putExtra("choose", 0);
                setResult(-1, intent);
                finish();
                break;
        }
    }

    @Override // androidx.fragment.app.FragmentActivity, android.app.Activity
    protected void onDestroy() {
        super.onDestroy();
        this.mMusicUtils.stop();
    }

    @Override // android.app.Activity, android.view.ContextThemeWrapper, android.content.ContextWrapper
    protected void attachBaseContext(Context context) {
        super.attachBaseContext(AppUtils.attachBaseContext(context));
    }

    public void setLanguage() {
        Locale language = AppUtils.getLanguage(PreferencesHelper.getSharedPreferences(getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(this)));
        if (language != null) {
            AppUtils.setLanguage(getApplicationContext(), language);
        }
    }
}
