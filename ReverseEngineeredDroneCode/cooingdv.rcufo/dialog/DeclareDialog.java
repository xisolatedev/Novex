package com.cooingdv.rcufo.dialog;

import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.text.SpannableStringBuilder;
import android.text.method.LinkMovementMethod;
import android.text.style.ClickableSpan;
import android.text.style.ForegroundColorSpan;
import android.util.DisplayMetrics;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.activity.DeclareActivity;
import com.cooingdv.rcufo.base.BaseDialogFragment;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.LocalUtil;
import com.vungle.ads.internal.protos.Sdk;

/* JADX INFO: loaded from: classes2.dex */
public class DeclareDialog extends BaseDialogFragment implements View.OnClickListener {
    private TextView tvAgree;
    private TextView tvContent;
    private TextView tvDisagree;

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_declare, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        this.tvDisagree = (TextView) viewInflate.findViewById(C3033R.id.dialog_declare_tv_disagree);
        this.tvAgree = (TextView) viewInflate.findViewById(C3033R.id.dialog_declare_tv_agree);
        this.tvContent = (TextView) viewInflate.findViewById(C3033R.id.dialog_declare_tv_content);
        this.tvDisagree.setOnClickListener(this);
        this.tvAgree.setOnClickListener(this);
        return viewInflate;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() == null || getDialog() == null || getDialog().getWindow() == null) {
            return;
        }
        initTextView();
        WindowManager.LayoutParams attributes = getDialog().getWindow().getAttributes();
        attributes.width = 250;
        attributes.height = 350;
        DisplayMetrics displayMetrics = getResources().getDisplayMetrics();
        if (getResources().getConfiguration().orientation == 2) {
            attributes.width = (displayMetrics.heightPixels * 4) / 5;
        } else if (getResources().getConfiguration().orientation == 1) {
            attributes.width = (displayMetrics.widthPixels * 3) / 5;
        }
        attributes.height = -2;
        attributes.gravity = 17;
        getDialog().getWindow().setAttributes(attributes);
        getDialog().setCanceledOnTouchOutside(true);
        getDialog().setCancelable(false);
    }

    private void initTextView() {
        int i;
        int i2;
        int i3;
        int i4;
        int i5;
        int i6 = PreferencesHelper.getSharedPreferences(getActivity().getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(getActivity()));
        SpannableStringBuilder spannableStringBuilder = new SpannableStringBuilder();
        spannableStringBuilder.append((CharSequence) getString(C3033R.string.dialog_string_declare_content));
        ClickableSpan clickableSpan = new ClickableSpan() { // from class: com.cooingdv.rcufo.dialog.DeclareDialog.1
            @Override // android.text.style.ClickableSpan
            public void onClick(View view) {
                DeclareDialog.this.startActivity(new Intent(DeclareDialog.this.getActivity(), (Class<?>) DeclareActivity.class));
            }
        };
        ClickableSpan clickableSpan2 = new ClickableSpan() { // from class: com.cooingdv.rcufo.dialog.DeclareDialog.2
            @Override // android.text.style.ClickableSpan
            public void onClick(View view) {
                DeclareDialog.this.startActivity(new Intent(DeclareDialog.this.getActivity(), (Class<?>) DeclareActivity.class));
            }
        };
        int i7 = 71;
        if (i6 != 0) {
            if (i6 == 2) {
                i7 = 265;
                i = 289;
                i2 = 293;
                i3 = 322;
            } else if (i6 == 3) {
                i7 = 294;
                i = Sdk.SDKError.Reason.AD_CLOSED_MISSING_HEARTBEAT_VALUE;
                i2 = 323;
                i3 = 346;
            } else {
                if (i6 == 4) {
                    i7 = 86;
                    i = 92;
                    i4 = 103;
                } else if (i6 == 5) {
                    i = 89;
                    i2 = 97;
                    i3 = 119;
                } else {
                    i = 85;
                    if (i6 == 6) {
                        i7 = 66;
                        i4 = 116;
                    } else if (i6 == 7) {
                        i7 = 69;
                        i2 = 88;
                        i3 = 114;
                    } else {
                        i7 = 205;
                        i = Sdk.SDKError.Reason.MRAID_JS_COPY_FAILED_VALUE;
                        i2 = 224;
                        i3 = 238;
                    }
                }
                i5 = 93;
                i3 = i4;
            }
            spannableStringBuilder.setSpan(clickableSpan, i7, i, 33);
            spannableStringBuilder.setSpan(clickableSpan2, i2, i3, 33);
            this.tvContent.setText(spannableStringBuilder);
            ForegroundColorSpan foregroundColorSpan = new ForegroundColorSpan(Color.parseColor("#303F9F"));
            ForegroundColorSpan foregroundColorSpan2 = new ForegroundColorSpan(Color.parseColor("#303F9F"));
            spannableStringBuilder.setSpan(foregroundColorSpan, i7, i, 33);
            spannableStringBuilder.setSpan(foregroundColorSpan2, i2, i3, 33);
            this.tvContent.setMovementMethod(LinkMovementMethod.getInstance());
            this.tvContent.setText(spannableStringBuilder);
        }
        i = 68;
        i3 = 75;
        i5 = 71;
        i7 = 64;
        i2 = i5;
        spannableStringBuilder.setSpan(clickableSpan, i7, i, 33);
        spannableStringBuilder.setSpan(clickableSpan2, i2, i3, 33);
        this.tvContent.setText(spannableStringBuilder);
        ForegroundColorSpan foregroundColorSpan3 = new ForegroundColorSpan(Color.parseColor("#303F9F"));
        ForegroundColorSpan foregroundColorSpan4 = new ForegroundColorSpan(Color.parseColor("#303F9F"));
        spannableStringBuilder.setSpan(foregroundColorSpan3, i7, i, 33);
        spannableStringBuilder.setSpan(foregroundColorSpan4, i2, i3, 33);
        this.tvContent.setMovementMethod(LinkMovementMethod.getInstance());
        this.tvContent.setText(spannableStringBuilder);
    }

    @Override // android.app.Fragment
    public void onResume() {
        super.onResume();
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onDetach() {
        super.onDetach();
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (view == null || getActivity() == null) {
            return;
        }
        int id = view.getId();
        if (id == C3033R.id.dialog_declare_tv_agree || id == C3033R.id.dialog_declare_tv_disagree) {
            dismiss();
        }
    }
}
