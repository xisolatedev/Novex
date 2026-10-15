package com.cooingdv.rcufo.utils;

import android.content.Context;
import android.media.AudioManager;
import android.media.MediaPlayer;
import com.cooingdv.rcufo.C3033R;

/* JADX INFO: loaded from: classes2.dex */
public class SoundUtils {
    private static MediaPlayer mMediaPlayer;

    public static void shootSound(Context context) {
        AudioManager audioManager = (AudioManager) context.getSystemService("audio");
        if (audioManager.getStreamVolume(4) == 0) {
            audioManager.setStreamVolume(3, audioManager.getStreamMaxVolume(3), 4);
        }
        MediaPlayer mediaPlayerCreate = MediaPlayer.create(context, C3033R.raw.camera_click);
        mMediaPlayer = mediaPlayerCreate;
        mediaPlayerCreate.setOnCompletionListener(new MediaPlayer.OnCompletionListener() { // from class: com.cooingdv.rcufo.utils.SoundUtils.1
            @Override // android.media.MediaPlayer.OnCompletionListener
            public void onCompletion(MediaPlayer mediaPlayer) {
                if (mediaPlayer != null) {
                    mediaPlayer.stop();
                    mediaPlayer.release();
                }
            }
        });
        mMediaPlayer.start();
    }

    public static void dingSound(Context context) {
        if (((AudioManager) context.getSystemService("audio")).getStreamVolume(4) != 0) {
            MediaPlayer mediaPlayerCreate = MediaPlayer.create(context, C3033R.raw.ding);
            mediaPlayerCreate.setOnCompletionListener(new MediaPlayer.OnCompletionListener() { // from class: com.cooingdv.rcufo.utils.SoundUtils.2
                @Override // android.media.MediaPlayer.OnCompletionListener
                public void onCompletion(MediaPlayer mediaPlayer) {
                    if (mediaPlayer != null) {
                        mediaPlayer.stop();
                        mediaPlayer.release();
                    }
                }
            });
            mediaPlayerCreate.start();
        }
    }

    public static void didiSound(boolean z, Context context) {
        if (((AudioManager) context.getSystemService("audio")).getStreamVolume(4) != 0) {
            MediaPlayer mediaPlayerCreate = MediaPlayer.create(context, z ? C3033R.raw.btn_middle : C3033R.raw.btn_turn);
            mediaPlayerCreate.setOnCompletionListener(new MediaPlayer.OnCompletionListener() { // from class: com.cooingdv.rcufo.utils.SoundUtils.3
                @Override // android.media.MediaPlayer.OnCompletionListener
                public void onCompletion(MediaPlayer mediaPlayer) {
                    if (mediaPlayer != null) {
                        mediaPlayer.stop();
                        mediaPlayer.release();
                    }
                }
            });
            mediaPlayerCreate.start();
        }
    }
}
