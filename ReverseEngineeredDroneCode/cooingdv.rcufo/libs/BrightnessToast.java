package com.cooingdv.rcufo.libs;

import android.app.Activity;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Toast;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.libs.verticalseekbar.VerticalSeekBar;
import com.cooingdv.rcufo.utils.AppUtils;

/* JADX INFO: loaded from: classes2.dex */
public class BrightnessToast {
    private static final int maxValue = 255;
    private Activity context;
    private VerticalSeekBar sbBrightness;
    private Toast toast;

    public static int getMaxValue() {
        return 255;
    }

    public BrightnessToast(Activity activity) {
        this.context = activity;
    }

    public void show(int i) {
        int screenBrightness = AppUtils.getScreenBrightness(this.context);
        if (this.toast == null) {
            this.toast = new Toast(this.context);
            View viewInflate = LayoutInflater.from(this.context).inflate(C3033R.layout.view_brightness, (ViewGroup) null);
            VerticalSeekBar verticalSeekBar = (VerticalSeekBar) viewInflate.findViewById(C3033R.id.view_brightness_seek_progress);
            this.sbBrightness = verticalSeekBar;
            verticalSeekBar.setMax(255);
            this.sbBrightness.setProgress(screenBrightness);
            this.toast.setView(viewInflate);
            this.toast.setGravity(17, 0, 0);
            this.toast.setDuration(0);
        }
        int iMin = Math.min(i + screenBrightness, 255);
        if (iMin >= 0) {
            this.sbBrightness.setProgress(iMin);
            AppUtils.setBrightness(this.context, iMin);
        } else {
            this.sbBrightness.setProgress(screenBrightness);
        }
        this.toast.show();
    }
}
