package com.cooingdv.rcufo.dialog;

import android.os.Bundle;
import android.text.method.ScrollingMovementMethod;
import android.util.DisplayMetrics;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.ProgressBar;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseDialogFragment;

/* JADX INFO: loaded from: classes2.dex */
public class NotifyDialog extends BaseDialogFragment {
    private OnConfirmClickListener mOnConfirmClickListener;
    private OnNegativeClickListener mOnNegativeClickListener;
    private OnPositiveClickListener mOnPositiveClickListener;
    private boolean isLeftGravity = false;
    private int mTitleId = 0;
    private int mContentId = 0;
    private int mNegativeButtonId = 0;
    private int mConfirmButtonId = 0;
    private int mPositiveButtonId = 0;
    private String mTitle = "";
    private String mContent = "";
    private boolean mShowProgressBar = false;

    public interface OnConfirmClickListener {
        void onClick();
    }

    public interface OnNegativeClickListener {
        void onClick();
    }

    public interface OnPositiveClickListener {
        void onClick();
    }

    public void setNotifyDialog(boolean z, int i) {
        this.mShowProgressBar = z;
        this.mContentId = i;
    }

    public void setNotifyDialog(boolean z, int i, int i2, OnConfirmClickListener onConfirmClickListener) {
        this.mShowProgressBar = z;
        this.mContentId = i;
        this.mConfirmButtonId = i2;
        this.mOnConfirmClickListener = onConfirmClickListener;
    }

    public void setNotifyDialog(int i, int i2, int i3, OnConfirmClickListener onConfirmClickListener) {
        this.mTitleId = i;
        this.mContentId = i2;
        this.mConfirmButtonId = i3;
        this.mOnConfirmClickListener = onConfirmClickListener;
    }

    public void setNotifyDialog(String str, String str2, int i, OnConfirmClickListener onConfirmClickListener) {
        this.mTitleId = -1;
        this.mTitle = str;
        this.mContentId = -1;
        this.mContent = str2;
        this.mConfirmButtonId = i;
        this.mOnConfirmClickListener = onConfirmClickListener;
    }

    public void setNotifyDialog(int i, int i2, int i3, int i4, OnNegativeClickListener onNegativeClickListener, OnPositiveClickListener onPositiveClickListener) {
        this.mTitleId = i;
        this.mContentId = i2;
        this.mPositiveButtonId = i4;
        this.mNegativeButtonId = i3;
        this.mOnNegativeClickListener = onNegativeClickListener;
        this.mOnPositiveClickListener = onPositiveClickListener;
    }

    public void setNotifyDialog(String str, String str2, int i, int i2, OnNegativeClickListener onNegativeClickListener, OnPositiveClickListener onPositiveClickListener) {
        this.mTitleId = -1;
        this.mTitle = str;
        this.mContentId = -1;
        this.mContent = str2;
        this.mPositiveButtonId = i2;
        this.mNegativeButtonId = i;
        this.mOnNegativeClickListener = onNegativeClickListener;
        this.mOnPositiveClickListener = onPositiveClickListener;
    }

    public void setContentTextLeft(boolean z) {
        this.isLeftGravity = z;
    }

    public void setContent(int i) {
        this.mContentId = i;
    }

    public void setContent(String str) {
        this.mContentId = -1;
        this.mContent = str;
    }

    public void setNegativeText(int i) {
        this.mNegativeButtonId = i;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setCancelable(false);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_notify, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        TextView textView = (TextView) viewInflate.findViewById(C3033R.id.tv_title);
        TextView textView2 = (TextView) viewInflate.findViewById(C3033R.id.tv_content);
        ProgressBar progressBar = (ProgressBar) viewInflate.findViewById(C3033R.id.progressBar);
        TextView textView3 = (TextView) viewInflate.findViewById(C3033R.id.tv_left);
        TextView textView4 = (TextView) viewInflate.findViewById(C3033R.id.tv_middle);
        TextView textView5 = (TextView) viewInflate.findViewById(C3033R.id.tv_right);
        View viewFindViewById = viewInflate.findViewById(C3033R.id.divider_id);
        View viewFindViewById2 = viewInflate.findViewById(C3033R.id.line_id);
        textView2.setMovementMethod(ScrollingMovementMethod.getInstance());
        if (this.mTitleId != 0) {
            progressBar.setVisibility(8);
            if (this.mTitleId == -1) {
                textView.setText(this.mTitle);
            } else {
                textView.setText(getResources().getString(this.mTitleId));
            }
        } else {
            textView.setVisibility(8);
            if (this.mShowProgressBar) {
                progressBar.setVisibility(0);
            } else {
                progressBar.setVisibility(8);
            }
        }
        if (this.mContentId != 0) {
            textView2.setVisibility(0);
            if (this.mContentId == -1) {
                textView2.setText(this.mContent);
            } else {
                textView2.setText(getResources().getString(this.mContentId));
            }
            if (this.isLeftGravity) {
                textView2.setGravity(3);
            } else {
                textView2.setGravity(17);
            }
        } else {
            textView2.setVisibility(8);
        }
        if (this.mNegativeButtonId != 0) {
            textView3.setVisibility(0);
            textView3.setText(getResources().getString(this.mNegativeButtonId));
        } else {
            textView3.setVisibility(8);
        }
        if (this.mConfirmButtonId != 0) {
            viewFindViewById2.setVisibility(0);
            viewFindViewById.setVisibility(8);
            textView4.setVisibility(0);
            textView4.setText(getResources().getString(this.mConfirmButtonId));
        } else {
            textView4.setVisibility(8);
            if (this.mShowProgressBar) {
                viewFindViewById2.setVisibility(8);
                viewFindViewById.setVisibility(8);
            } else {
                viewFindViewById2.setVisibility(0);
                viewFindViewById.setVisibility(0);
            }
        }
        if (this.mPositiveButtonId != 0) {
            textView5.setVisibility(0);
            textView5.setText(getResources().getString(this.mPositiveButtonId));
        } else {
            textView5.setVisibility(8);
        }
        textView4.setOnClickListener(new View.OnClickListener() { // from class: com.cooingdv.rcufo.dialog.NotifyDialog.1
            @Override // android.view.View.OnClickListener
            public void onClick(View view) {
                if (NotifyDialog.this.mOnConfirmClickListener != null) {
                    NotifyDialog.this.mOnConfirmClickListener.onClick();
                }
                NotifyDialog.this.dismiss();
            }
        });
        textView3.setOnClickListener(new View.OnClickListener() { // from class: com.cooingdv.rcufo.dialog.NotifyDialog.2
            @Override // android.view.View.OnClickListener
            public void onClick(View view) {
                if (NotifyDialog.this.mOnNegativeClickListener != null) {
                    NotifyDialog.this.mOnNegativeClickListener.onClick();
                }
                NotifyDialog.this.dismiss();
            }
        });
        textView5.setOnClickListener(new View.OnClickListener() { // from class: com.cooingdv.rcufo.dialog.NotifyDialog.3
            @Override // android.view.View.OnClickListener
            public void onClick(View view) {
                if (NotifyDialog.this.mOnPositiveClickListener != null) {
                    NotifyDialog.this.mOnPositiveClickListener.onClick();
                }
                NotifyDialog.this.dismiss();
            }
        });
        return viewInflate;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() == null || getDialog() == null || getDialog().getWindow() == null) {
            return;
        }
        WindowManager.LayoutParams attributes = getDialog().getWindow().getAttributes();
        attributes.width = 100;
        attributes.height = 50;
        DisplayMetrics displayMetrics = getResources().getDisplayMetrics();
        if (getResources().getConfiguration().orientation == 2) {
            attributes.width = (displayMetrics.heightPixels * 4) / 5;
            attributes.height = (displayMetrics.heightPixels * 2) / 4;
        } else if (getResources().getConfiguration().orientation == 1) {
            attributes.width = (displayMetrics.widthPixels * 4) / 5;
            attributes.height = (displayMetrics.widthPixels * 2) / 4;
        }
        attributes.gravity = 17;
        getDialog().getWindow().setAttributes(attributes);
        getDialog().getWindow().setBackgroundDrawableResource(C3033R.drawable.bg_dialog);
    }

    public void release() {
        this.mOnPositiveClickListener = null;
        this.mOnConfirmClickListener = null;
        this.mOnNegativeClickListener = null;
    }
}
