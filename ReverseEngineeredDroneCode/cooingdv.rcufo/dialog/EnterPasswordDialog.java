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
public class EnterPasswordDialog extends BaseDialogFragment implements View.OnClickListener {
    private TextView btnCancel;
    private EditText editPassword;
    private boolean isHiddenCancel;
    private boolean isSetTitle;
    private TextView tvTitle;
    private View viewDivider;

    public void setHiddenCancel() {
        this.isHiddenCancel = true;
    }

    public void setTitle() {
        this.isSetTitle = true;
    }

    public boolean isHiddenCancel() {
        return this.isHiddenCancel;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_enter_password, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        EditText editText = (EditText) viewInflate.findViewById(C3033R.id.dialog_enter_pwd_edit);
        this.editPassword = editText;
        editText.setFilters(new InputFilter[]{new InputFilter.LengthFilter(8)});
        this.btnCancel = (TextView) viewInflate.findViewById(C3033R.id.dialog_enter_pwd_cancel);
        this.tvTitle = (TextView) viewInflate.findViewById(C3033R.id.dialog_enter_pwd_tv);
        TextView textView = (TextView) viewInflate.findViewById(C3033R.id.dialog_enter_pwd_ok);
        this.viewDivider = viewInflate.findViewById(C3033R.id.dialog_enter_pwd_divider);
        this.btnCancel.setOnClickListener(this);
        textView.setOnClickListener(this);
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
        if (this.isHiddenCancel) {
            this.btnCancel.setVisibility(8);
            this.viewDivider.setVisibility(8);
        }
        if (this.isSetTitle) {
            this.tvTitle.setText(getString(C3033R.string.change_password));
        }
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
        if (getActivity() == null || getDialog() == null || view == null) {
            return;
        }
        int id = view.getId();
        if (id == C3033R.id.dialog_enter_pwd_cancel) {
            dismiss();
            return;
        }
        if (id != C3033R.id.dialog_enter_pwd_ok) {
            return;
        }
        String strTrim = this.editPassword.getText().toString().trim();
        if (!TextUtils.isEmpty(strTrim) && strTrim.length() == 8) {
            SocketClient.getInstance().debugSend(new byte[]{10, (byte) Integer.parseInt(strTrim.substring(0, 1)), (byte) Integer.parseInt(strTrim.substring(1, 2)), (byte) Integer.parseInt(strTrim.substring(2, 3)), (byte) Integer.parseInt(strTrim.substring(3, 4)), (byte) Integer.parseInt(strTrim.substring(4, 5)), (byte) Integer.parseInt(strTrim.substring(5, 6)), (byte) Integer.parseInt(strTrim.substring(6, 7)), (byte) Integer.parseInt(strTrim.substring(7))});
        } else {
            showShortToast(C3033R.string.enter_password_tip);
        }
    }
}
