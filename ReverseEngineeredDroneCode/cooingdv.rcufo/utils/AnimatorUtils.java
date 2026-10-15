package com.cooingdv.rcufo.utils;

import android.view.View;
import android.view.animation.AlphaAnimation;
import android.view.animation.LinearInterpolator;

/* JADX INFO: loaded from: classes2.dex */
public class AnimatorUtils {
    public static void startFlick(View view) {
        if (view == null) {
            return;
        }
        view.setVisibility(0);
        AlphaAnimation alphaAnimation = new AlphaAnimation(1.0f, 0.0f);
        alphaAnimation.setDuration(500L);
        alphaAnimation.setInterpolator(new LinearInterpolator());
        alphaAnimation.setRepeatCount(-1);
        alphaAnimation.setRepeatMode(2);
        view.startAnimation(alphaAnimation);
    }

    public static void stopFlick(View view) {
        if (view == null) {
            return;
        }
        view.setVisibility(4);
        view.clearAnimation();
    }
}
