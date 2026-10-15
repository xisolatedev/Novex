package com.cooingdv.rcufo.dialog;

import android.os.Bundle;
import android.util.DisplayMetrics;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.RadioButton;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseDialogFragment;

/* JADX INFO: loaded from: classes2.dex */
public class SelectResolutionDialog extends BaseDialogFragment implements View.OnClickListener {
    private RadioButton btn1080P;
    private RadioButton btn4K;
    private RadioButton btn720P;
    private int resolution = 0;
    private TextView tvCancel;
    private TextView tvConfirm;

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_select_resolution, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        this.btn720P = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_resolution_720p);
        this.btn1080P = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_resolution_1080p);
        this.btn4K = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_resolution_4k);
        this.tvCancel = (TextView) viewInflate.findViewById(C3033R.id.dialog_select_resolution_cancel);
        this.tvConfirm = (TextView) viewInflate.findViewById(C3033R.id.dialog_select_resolution_ok);
        this.btn720P.setOnClickListener(this);
        this.btn1080P.setOnClickListener(this);
        this.btn4K.setOnClickListener(this);
        this.tvCancel.setOnClickListener(this);
        this.tvConfirm.setOnClickListener(this);
        return viewInflate;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() == null || getDialog() == null || getDialog().getWindow() == null) {
            return;
        }
        WindowManager.LayoutParams attributes = getDialog().getWindow().getAttributes();
        attributes.width = 250;
        attributes.height = 350;
        DisplayMetrics displayMetrics = getResources().getDisplayMetrics();
        if (getResources().getConfiguration().orientation == 2) {
            attributes.width = (displayMetrics.heightPixels * 3) / 5;
        } else if (getResources().getConfiguration().orientation == 1) {
            attributes.width = (displayMetrics.widthPixels * 3) / 5;
        }
        attributes.height = -2;
        attributes.gravity = 17;
        getDialog().getWindow().setAttributes(attributes);
        getDialog().setCanceledOnTouchOutside(true);
        getDialog().getWindow().setBackgroundDrawableResource(C3033R.drawable.bg_dialog);
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
        switch (view.getId()) {
            case C3033R.id.dialog_select_resolution_1080p /* 2131296568 */:
                this.resolution = 29;
                break;
            case C3033R.id.dialog_select_resolution_4k /* 2131296569 */:
                this.resolution = 30;
                break;
            case C3033R.id.dialog_select_resolution_720p /* 2131296570 */:
                this.resolution = 27;
                break;
            case C3033R.id.dialog_select_resolution_cancel /* 2131296571 */:
                dismiss();
                break;
            case C3033R.id.dialog_select_resolution_ok /* 2131296572 */:
                if (this.resolution == 0) {
                    showShortToast(getString(C3033R.string.firmware_setting_resolution_toast));
                } else {
                    dismiss();
                }
                break;
        }
    }
}
