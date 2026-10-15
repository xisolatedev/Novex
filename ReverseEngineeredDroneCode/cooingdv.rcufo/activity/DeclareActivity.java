package com.cooingdv.rcufo.activity;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.os.Bundle;
import android.text.SpannableStringBuilder;
import android.text.method.LinkMovementMethod;
import android.text.style.ClickableSpan;
import android.text.style.ForegroundColorSpan;
import android.view.View;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.view.OnApplyWindowInsetsListener;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.LocalUtil;
import com.mbridge.msdk.playercommon.exoplayer2.C9483C;
import java.util.Locale;

/* JADX INFO: loaded from: classes2.dex */
public class DeclareActivity extends Activity implements View.OnClickListener {
    private int flag;
    private LinearLayout layoutDeclare;
    private TextView mTextView;
    private WebView mWebView;

    @Override // android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        getWindow().setFlags(1024, 1024);
        setContentView(C3033R.layout.activity_declare);
        LinearLayout linearLayout = (LinearLayout) findViewById(C3033R.id.declare_layout);
        this.layoutDeclare = (LinearLayout) findViewById(C3033R.id.layout_declare);
        this.mWebView = (WebView) findViewById(C3033R.id.declare_privacy_policy_webview);
        this.mTextView = (TextView) findViewById(C3033R.id.declare_tv);
        ((ImageView) findViewById(C3033R.id.declare_back_btn)).setOnClickListener(this);
        initWebView();
        initTextView();
        ViewCompat.setOnApplyWindowInsetsListener(linearLayout, new OnApplyWindowInsetsListener() { // from class: com.cooingdv.rcufo.activity.DeclareActivity$$ExternalSyntheticLambda0
            @Override // androidx.core.view.OnApplyWindowInsetsListener
            public final WindowInsetsCompat onApplyWindowInsets(View view, WindowInsetsCompat windowInsetsCompat) {
                return DeclareActivity.lambda$onCreate$0(view, windowInsetsCompat);
            }
        });
    }

    static /* synthetic */ WindowInsetsCompat lambda$onCreate$0(View view, WindowInsetsCompat windowInsetsCompat) {
        view.setPadding(0, 0, windowInsetsCompat.getInsets(WindowInsetsCompat.Type.navigationBars()).right, 0);
        return windowInsetsCompat;
    }

    private void initTextView() {
        int i;
        int i2;
        int i3;
        int i4 = PreferencesHelper.getSharedPreferences(getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(this));
        SpannableStringBuilder spannableStringBuilder = new SpannableStringBuilder();
        spannableStringBuilder.append((CharSequence) "\u3000\u3000").append((CharSequence) getString(C3033R.string.string_declare1));
        ClickableSpan clickableSpan = new ClickableSpan() { // from class: com.cooingdv.rcufo.activity.DeclareActivity.1
            @Override // android.text.style.ClickableSpan
            public void onClick(View view) {
                if (DeclareActivity.this.layoutDeclare.getVisibility() == 0) {
                    DeclareActivity.this.layoutDeclare.setVisibility(8);
                }
                if (DeclareActivity.this.flag == 0) {
                    DeclareActivity.this.mWebView.loadUrl("file:///android_asset/user_agreement_chinese.html");
                } else {
                    DeclareActivity.this.mWebView.loadUrl("file:///android_asset/user_agreement_english.html");
                }
                DeclareActivity.this.mWebView.setVisibility(0);
            }
        };
        ClickableSpan clickableSpan2 = new ClickableSpan() { // from class: com.cooingdv.rcufo.activity.DeclareActivity.2
            @Override // android.text.style.ClickableSpan
            public void onClick(View view) {
                if (DeclareActivity.this.layoutDeclare.getVisibility() == 0) {
                    DeclareActivity.this.layoutDeclare.setVisibility(8);
                }
                if (DeclareActivity.this.flag == 0) {
                    DeclareActivity.this.mWebView.loadUrl("file:///android_asset/privacy_policy_chinese.html");
                } else {
                    DeclareActivity.this.mWebView.loadUrl("file:///android_asset/privacy_policy_english.html");
                }
                DeclareActivity.this.mWebView.setVisibility(0);
            }
        };
        int i5 = 19;
        if (i4 == 0) {
            i2 = 23;
            i = 16;
            i3 = 19;
            i5 = 12;
        } else if (i4 == 2) {
            i5 = 27;
            i = 50;
            i2 = 82;
            i3 = 54;
        } else {
            i = 47;
            int i6 = 28;
            if (i4 == 3) {
                i2 = 76;
                i3 = 52;
            } else if (i4 == 4) {
                i2 = 36;
                i = 25;
                i3 = 28;
            } else if (i4 == 5) {
                i3 = 50;
                i5 = 28;
                i2 = 73;
            } else {
                i2 = 63;
                i3 = 49;
                i = 44;
                i6 = 30;
                if (i4 != 6 && i4 == 7) {
                    i2 = 85;
                    i = 53;
                    i3 = 60;
                    i5 = 33;
                }
            }
            i5 = i6;
        }
        spannableStringBuilder.setSpan(clickableSpan, i5, i, 33);
        spannableStringBuilder.setSpan(clickableSpan2, i3, i2, 33);
        this.mTextView.setText(spannableStringBuilder);
        ForegroundColorSpan foregroundColorSpan = new ForegroundColorSpan(Color.parseColor("#303F9F"));
        ForegroundColorSpan foregroundColorSpan2 = new ForegroundColorSpan(Color.parseColor("#303F9F"));
        spannableStringBuilder.setSpan(foregroundColorSpan, i5, i, 33);
        spannableStringBuilder.setSpan(foregroundColorSpan2, i3, i2, 33);
        this.mTextView.setMovementMethod(LinkMovementMethod.getInstance());
        this.mTextView.setText(spannableStringBuilder);
    }

    private void initWebView() {
        this.mWebView.setWebViewClient(new WebViewClient());
        this.mWebView.setScrollBarStyle(0);
        WebSettings settings = this.mWebView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDefaultTextEncodingName(C9483C.UTF8_NAME);
        settings.setBuiltInZoomControls(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
    }

    @Override // android.app.Activity
    protected void onStart() {
        super.onStart();
        setLanguage();
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (view.getId() != C3033R.id.declare_back_btn) {
            return;
        }
        if (this.layoutDeclare.getVisibility() != 0) {
            this.layoutDeclare.setVisibility(0);
            this.mWebView.setVisibility(8);
        } else {
            finish();
        }
    }

    @Override // android.app.Activity
    public void onBackPressed() {
        if (this.layoutDeclare.getVisibility() != 0) {
            this.layoutDeclare.setVisibility(0);
            this.mWebView.setVisibility(8);
        } else {
            super.onBackPressed();
        }
    }

    @Override // android.app.Activity, android.view.ContextThemeWrapper, android.content.ContextWrapper
    protected void attachBaseContext(Context context) {
        super.attachBaseContext(AppUtils.attachBaseContext(context));
    }

    public void setLanguage() {
        int i = PreferencesHelper.getSharedPreferences(this).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(this));
        this.flag = i;
        Locale language = AppUtils.getLanguage(i);
        if (language != null) {
            AppUtils.setLanguage(getApplicationContext(), language);
        }
    }
}
