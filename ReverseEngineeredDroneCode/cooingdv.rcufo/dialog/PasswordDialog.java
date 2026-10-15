package com.cooingdv.rcufo.dialog;

import android.os.Bundle;
import android.text.InputFilter;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseDialogFragment;
import com.cooingdv.rcufo.socket.SocketClient;

/* JADX INFO: loaded from: classes2.dex */
public class PasswordDialog extends BaseDialogFragment implements View.OnClickListener {
    private EditText editPassword;

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_password, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        EditText editText = (EditText) viewInflate.findViewById(C3033R.id.dialog_pwd_edit);
        this.editPassword = editText;
        editText.setFilters(new InputFilter[]{new InputFilter.LengthFilter(8)});
        ((TextView) viewInflate.findViewById(C3033R.id.dialog_pwd_ok)).setOnClickListener(this);
        return viewInflate;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() == null || getDialog() == null || getDialog().getWindow() == null) {
            return;
        }
        WindowManager.LayoutParams attributes = getDialog().getWindow().getAttributes();
        attributes.width = -2;
        attributes.height = -2;
        attributes.gravity = 17;
        setCancelable(false);
        getDialog().getWindow().setAttributes(attributes);
        getDialog().getWindow().setBackgroundDrawableResource(C3033R.drawable.bg_dialog);
    }

    @Override // android.app.Fragment
    public void onResume() {
        super.onResume();
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public void onDestroy() {
        super.onDestroy();
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (getActivity() == null || getDialog() == null || view == null || view.getId() != C3033R.id.dialog_pwd_ok) {
            return;
        }
        String strTrim = this.editPassword.getText().toString().trim();
        if (TextUtils.isEmpty(strTrim)) {
            showShortToast(C3033R.string.enter_password_tip);
            return;
        }
        if (strTrim.length() == 8) {
            if (strTrim.equals(SocketClient.getInstance().getWifiPassword())) {
                showShortToast(C3033R.string.enter_password_correct);
                SocketClient.getInstance().setPasswordCorrect(true);
                dismiss();
                return;
            }
            showShortToast(C3033R.string.enter_password_error);
            return;
        }
        showShortToast(C3033R.string.enter_password_error);
    }
}
