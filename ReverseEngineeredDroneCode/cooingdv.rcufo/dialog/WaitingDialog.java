package com.cooingdv.rcufo.dialog;

import android.content.DialogInterface;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseDialogFragment;

/* JADX INFO: loaded from: classes2.dex */
public class WaitingDialog extends BaseDialogFragment implements DialogInterface.OnKeyListener {
    private String notifyContent;
    private OnWaitingDialog onWaitingDialog;
    private TextView tvNotifyContent;

    public interface OnWaitingDialog {
        void onCancelDialog();
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_waiting, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        this.tvNotifyContent = (TextView) viewInflate.findViewById(C3033R.id.dialog_waiting_tv);
        return viewInflate;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() == null || getDialog() == null || getDialog().getWindow() == null) {
            return;
        }
        TextView textView = this.tvNotifyContent;
        if (textView != null && textView.getVisibility() == 0) {
            this.tvNotifyContent.setText(this.notifyContent);
        }
        WindowManager.LayoutParams attributes = getDialog().getWindow().getAttributes();
        attributes.width = -2;
        attributes.height = -2;
        attributes.gravity = 17;
        getDialog().getWindow().setAttributes(attributes);
        getDialog().getWindow().setBackgroundDrawableResource(C3033R.drawable.bg_dialog);
        getDialog().setOnKeyListener(this);
    }

    @Override // android.app.Fragment
    public void onResume() {
        super.onResume();
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onDetach() {
        super.onDetach();
    }

    @Override // android.content.DialogInterface.OnKeyListener
    public boolean onKey(DialogInterface dialogInterface, int i, KeyEvent keyEvent) {
        if (i != 4) {
            return false;
        }
        OnWaitingDialog onWaitingDialog = this.onWaitingDialog;
        if (onWaitingDialog != null) {
            onWaitingDialog.onCancelDialog();
        }
        dismiss();
        return true;
    }

    public void setNotifyContent(String str) {
        this.notifyContent = str;
    }

    public void setOnWaitingDialog(OnWaitingDialog onWaitingDialog) {
        this.onWaitingDialog = onWaitingDialog;
    }
}
