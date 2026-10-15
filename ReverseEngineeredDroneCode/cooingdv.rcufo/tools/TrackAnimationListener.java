package com.cooingdv.rcufo.tools;

import android.animation.Animator;
import android.graphics.Point;
import android.view.View;
import android.view.animation.LinearInterpolator;
import com.cooingdv.rcufo.libs.TrackView;
import com.vungle.ads.internal.protos.Sdk;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class TrackAnimationListener implements Animator.AnimatorListener {
    View air;
    float centerPointX;
    float centerPointY;
    private AnimatorTrackListener listener;
    List<Point> lpoints;
    List<Point> points;
    int screenWidth;
    int screenheight;
    TrackView trackView;
    int size = 1;
    private int radius = Sdk.SDKError.Reason.INVALID_GZIP_BID_PAYLOAD_VALUE;
    int duration = 500;

    public interface AnimatorTrackListener {
        void trackFly(float f, float f2);
    }

    @Override // android.animation.Animator.AnimatorListener
    public void onAnimationRepeat(Animator animator) {
    }

    @Override // android.animation.Animator.AnimatorListener
    public void onAnimationStart(Animator animator) {
    }

    public TrackAnimationListener(List<Point> list, List<Point> list2, View view, TrackView trackView, int i, int i2, AnimatorTrackListener animatorTrackListener) {
        this.points = list;
        this.lpoints = list2;
        this.air = view;
        this.trackView = trackView;
        this.screenWidth = i;
        this.screenheight = i2;
        this.centerPointX = list.get(0).x;
        this.centerPointY = list.get(0).y;
        this.listener = animatorTrackListener;
    }

    @Override // android.animation.Animator.AnimatorListener
    public void onAnimationEnd(Animator animator) {
        if (this.size < this.points.size()) {
            float f = this.points.get(this.size).x - this.centerPointX;
            float f2 = this.centerPointY - this.points.get(this.size).y;
            int size = this.points.size() - 1;
            int i = this.size;
            if (size > i) {
                if (f > 0.0f && this.points.get(i).x > this.points.get(this.size + 1).x) {
                    this.centerPointX = this.points.get(this.size).x;
                    this.centerPointY = this.points.get(this.size).y;
                }
                if (f < 0.0f && this.points.get(this.size).x < this.points.get(this.size + 1).x) {
                    this.centerPointX = this.points.get(this.size).x;
                    this.centerPointY = this.points.get(this.size).y;
                }
                if (f2 > 0.0f && this.points.get(this.size).y < this.points.get(this.size + 1).y) {
                    this.centerPointX = this.points.get(this.size).x;
                    this.centerPointY = this.points.get(this.size).y;
                }
                if (f2 < 0.0f && this.points.get(this.size).y > this.points.get(this.size + 1).y) {
                    this.centerPointX = this.points.get(this.size).x;
                    this.centerPointY = this.points.get(this.size).y;
                }
            }
            int i2 = this.radius;
            if (f < (-i2)) {
                f = -i2;
            }
            if (f > i2) {
                f = i2;
            }
            if (f2 < (-i2)) {
                f2 = -i2;
            }
            if (f2 > i2) {
                f2 = i2;
            }
            this.listener.trackFly(f, f2);
            float fAbs = Math.abs(this.points.get(this.size).x - this.points.get(this.size - 1).x);
            float fAbs2 = Math.abs(this.points.get(this.size).y - this.points.get(this.size - 1).y);
            if (fAbs > fAbs2) {
                this.duration = (int) (fAbs * 10.0f);
            } else {
                this.duration = (int) (fAbs2 * 10.0f);
            }
            this.air.animate().translationX(this.points.get(this.size).x - (this.screenWidth / 2)).translationY(this.points.get(this.size).y - (this.screenheight / 2)).setInterpolator(new LinearInterpolator()).setDuration(this.duration).setListener(this);
            this.size++;
            return;
        }
        clearTrack();
    }

    @Override // android.animation.Animator.AnimatorListener
    public void onAnimationCancel(Animator animator) {
        clearTrack();
    }

    private void clearTrack() {
        this.listener.trackFly(0.0f, 0.0f);
        View view = this.air;
        if (view != null) {
            view.setVisibility(8);
            this.air = null;
        }
        this.points.clear();
        this.lpoints.clear();
        this.trackView.postInvalidate();
        this.trackView.stopTracking();
    }
}
