package com.cooingdv.rcufo.dialog;

import android.os.Bundle;
import android.util.DisplayMetrics;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.RadioButton;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseDialogFragment;

/* JADX INFO: loaded from: classes2.dex */
public class SelectLanguageDialog extends BaseDialogFragment implements View.OnClickListener {
    private RadioButton btnChinese;
    private RadioButton btnEnglish;
    private RadioButton btnFrench;
    private RadioButton btnGerman;
    private RadioButton btnItalian;
    private RadioButton btnJapanese;
    private RadioButton btnPortuguese;
    private RadioButton btnSpanish;
    private int languageFlag = 0;
    private OnSelectLanguageListener onSelectLanguageListener;

    public interface OnSelectLanguageListener {
        void onSelectLanguage(int i);
    }

    public void setLanguageFlag(int i) {
        this.languageFlag = i;
    }

    public void setOnSelectLanguageListener(OnSelectLanguageListener onSelectLanguageListener) {
        this.onSelectLanguageListener = onSelectLanguageListener;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_select_language, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        this.btnChinese = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_chinese);
        this.btnEnglish = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_english);
        this.btnFrench = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_french);
        this.btnGerman = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_german);
        this.btnJapanese = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_japanese);
        this.btnSpanish = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_spanish);
        this.btnPortuguese = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_portuguese);
        this.btnItalian = (RadioButton) viewInflate.findViewById(C3033R.id.dialog_select_language_italian);
        this.btnChinese.setOnClickListener(this);
        this.btnEnglish.setOnClickListener(this);
        this.btnFrench.setOnClickListener(this);
        this.btnGerman.setOnClickListener(this);
        this.btnJapanese.setOnClickListener(this);
        this.btnSpanish.setOnClickListener(this);
        this.btnPortuguese.setOnClickListener(this);
        this.btnItalian.setOnClickListener(this);
        return viewInflate;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() == null || getDialog() == null || getDialog().getWindow() == null) {
            return;
        }
        int i = this.languageFlag;
        if (i == 0) {
            this.btnChinese.setChecked(true);
        } else if (i == 2) {
            this.btnFrench.setChecked(true);
        } else if (i == 3) {
            this.btnGerman.setChecked(true);
        } else if (i == 4) {
            this.btnJapanese.setChecked(true);
        } else if (i == 5) {
            this.btnSpanish.setChecked(true);
        } else if (i == 6) {
            this.btnPortuguese.setChecked(true);
        } else if (i == 7) {
            this.btnItalian.setChecked(true);
        } else {
            this.btnEnglish.setChecked(true);
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
            case C3033R.id.dialog_select_language_chinese /* 2131296559 */:
                OnSelectLanguageListener onSelectLanguageListener = this.onSelectLanguageListener;
                if (onSelectLanguageListener != null) {
                    onSelectLanguageListener.onSelectLanguage(0);
                }
                dismiss();
                break;
            case C3033R.id.dialog_select_language_english /* 2131296560 */:
                OnSelectLanguageListener onSelectLanguageListener2 = this.onSelectLanguageListener;
                if (onSelectLanguageListener2 != null) {
                    onSelectLanguageListener2.onSelectLanguage(1);
                }
                dismiss();
                break;
            case C3033R.id.dialog_select_language_french /* 2131296561 */:
                OnSelectLanguageListener onSelectLanguageListener3 = this.onSelectLanguageListener;
                if (onSelectLanguageListener3 != null) {
                    onSelectLanguageListener3.onSelectLanguage(2);
                }
                dismiss();
                break;
            case C3033R.id.dialog_select_language_german /* 2131296562 */:
                OnSelectLanguageListener onSelectLanguageListener4 = this.onSelectLanguageListener;
                if (onSelectLanguageListener4 != null) {
                    onSelectLanguageListener4.onSelectLanguage(3);
                }
                dismiss();
                break;
            case C3033R.id.dialog_select_language_italian /* 2131296563 */:
                OnSelectLanguageListener onSelectLanguageListener5 = this.onSelectLanguageListener;
                if (onSelectLanguageListener5 != null) {
                    onSelectLanguageListener5.onSelectLanguage(7);
                }
                dismiss();
                break;
            case C3033R.id.dialog_select_language_japanese /* 2131296564 */:
                OnSelectLanguageListener onSelectLanguageListener6 = this.onSelectLanguageListener;
                if (onSelectLanguageListener6 != null) {
                    onSelectLanguageListener6.onSelectLanguage(4);
                }
                dismiss();
                break;
            case C3033R.id.dialog_select_language_portuguese /* 2131296565 */:
                OnSelectLanguageListener onSelectLanguageListener7 = this.onSelectLanguageListener;
                if (onSelectLanguageListener7 != null) {
                    onSelectLanguageListener7.onSelectLanguage(6);
                }
                dismiss();
                break;
            case C3033R.id.dialog_select_language_spanish /* 2131296566 */:
                OnSelectLanguageListener onSelectLanguageListener8 = this.onSelectLanguageListener;
                if (onSelectLanguageListener8 != null) {
                    onSelectLanguageListener8.onSelectLanguage(5);
                }
                dismiss();
                break;
        }
    }
}
