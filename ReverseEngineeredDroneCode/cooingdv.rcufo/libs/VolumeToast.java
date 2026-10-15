package com.cooingdv.rcufo.libs;

import android.content.Context;
import android.media.AudioManager;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Toast;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.libs.verticalseekbar.VerticalSeekBar;

/* JADX INFO: loaded from: classes2.dex */
public class VolumeToast {
    private AudioManager mAudioManager;
    private Context mContext;
    private int maxVol;
    private VerticalSeekBar sbVolume;
    private Toast toast;

    public VolumeToast(Context context) {
        this.mContext = context;
        AudioManager audioManager = (AudioManager) context.getSystemService("audio");
        this.mAudioManager = audioManager;
        this.maxVol = audioManager.getStreamMaxVolume(3);
    }

    public void show(int i) {
        int streamVolume = this.mAudioManager.getStreamVolume(3);
        if (this.toast == null) {
            this.toast = new Toast(this.mContext);
            View viewInflate = LayoutInflater.from(this.mContext).inflate(C3033R.layout.view_volume, (ViewGroup) null);
            VerticalSeekBar verticalSeekBar = (VerticalSeekBar) viewInflate.findViewById(C3033R.id.view_volume_seek_progress);
            this.sbVolume = verticalSeekBar;
            verticalSeekBar.setMax(this.maxVol);
            this.sbVolume.setProgress(streamVolume);
            this.toast.setView(viewInflate);
            this.toast.setGravity(17, 0, 0);
            this.toast.setDuration(0);
        }
        int iMin = Math.min(i + streamVolume, this.maxVol);
        if (iMin >= 0) {
            this.sbVolume.setProgress(iMin);
            this.mAudioManager.setStreamVolume(3, iMin, 0);
        } else {
            this.sbVolume.setProgress(streamVolume);
        }
        this.toast.show();
    }

    public int getMaxVol() {
        return this.maxVol;
    }
}
