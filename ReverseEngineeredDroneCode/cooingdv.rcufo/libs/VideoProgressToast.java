package com.cooingdv.rcufo.libs;

import android.content.Context;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;
import com.cooingdv.rcufo.C3033R;

/* JADX INFO: loaded from: classes2.dex */
public class VideoProgressToast {
    public static final int FAST_BACKWARD = 4139;
    public static final int FAST_FORWARD = 4138;
    private ImageView ivFastBackward;
    private ImageView ivFastForward;
    private Context mContext;
    private Toast toast;
    private TextView tvText;

    public VideoProgressToast(Context context) {
        this.mContext = context;
    }

    public void show(int i, String str) {
        if (this.toast == null) {
            this.toast = new Toast(this.mContext);
            View viewInflate = LayoutInflater.from(this.mContext).inflate(C3033R.layout.view_video_progress, (ViewGroup) null);
            this.ivFastForward = (ImageView) viewInflate.findViewById(C3033R.id.view_video_fast_forward);
            this.tvText = (TextView) viewInflate.findViewById(C3033R.id.view_video_tv);
            this.ivFastBackward = (ImageView) viewInflate.findViewById(C3033R.id.view_video_fast_backward);
            this.toast.setView(viewInflate);
            this.toast.setGravity(17, 0, 0);
            this.toast.setDuration(0);
        }
        if (i == 4138) {
            this.ivFastBackward.setVisibility(8);
            this.ivFastForward.setVisibility(0);
            this.tvText.setText(this.mContext.getString(C3033R.string.fast_forward));
        } else if (i == 4139) {
            this.ivFastForward.setVisibility(8);
            this.ivFastBackward.setVisibility(0);
            this.tvText.setText(this.mContext.getString(C3033R.string.fast_backward));
        }
        if (!TextUtils.isEmpty(str)) {
            this.tvText.setText(str);
        }
        this.toast.show();
    }
}
