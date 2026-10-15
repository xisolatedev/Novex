package com.cooingdv.rcufo.libs;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Point;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class TrackView extends View {
    private List<Point> allPoints;
    private boolean isStartTrack;
    private Paint mPaint;
    private List<Point> movePoints;
    private OnTrackListener onTrackListener;

    public interface OnTrackListener {
        void onTrackStart(List<Point> list, List<Point> list2);

        void onTrackStop();
    }

    public void stopTracking() {
        this.isStartTrack = false;
    }

    public TrackView(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
        this.allPoints = new ArrayList();
        this.isStartTrack = false;
        super.setOnTouchListener(new OnTouchListenerImp());
    }

    private class OnTouchListenerImp implements View.OnTouchListener {
        private OnTouchListenerImp() {
        }

        @Override // android.view.View.OnTouchListener
        public boolean onTouch(View view, MotionEvent motionEvent) {
            Point point = new Point((int) motionEvent.getX(), (int) motionEvent.getY());
            if (motionEvent.getAction() == 0) {
                TrackView.this.allPoints = new ArrayList();
                TrackView.this.allPoints.add(point);
                TrackView.this.movePoints = new ArrayList();
                TrackView.this.movePoints.add(point);
                TrackView.this.onTrackListener.onTrackStop();
                TrackView.this.isStartTrack = false;
            } else if (motionEvent.getAction() == 1) {
                if (!TrackView.this.isStartTrack) {
                    TrackView.this.onTrackListener.onTrackStart(TrackView.this.movePoints, TrackView.this.allPoints);
                }
            } else if (motionEvent.getAction() == 2) {
                if (point.x < 0 && !TrackView.this.isStartTrack) {
                    TrackView.this.onTrackListener.onTrackStart(TrackView.this.movePoints, TrackView.this.allPoints);
                    TrackView.this.isStartTrack = true;
                }
                if (!TrackView.this.allPoints.contains(point) && !TrackView.this.isStartTrack) {
                    Point point2 = (Point) TrackView.this.allPoints.get(TrackView.this.allPoints.size() - 1);
                    if (point2.x - point.x > 20 || point2.x - point.x < -20 || point2.y - point.y > 20 || point2.y - point.y < -20) {
                        TrackView.this.allPoints.add(point);
                        TrackView.this.postInvalidate();
                    }
                }
                if (!TrackView.this.movePoints.contains(point) && !TrackView.this.isStartTrack) {
                    Point point3 = (Point) TrackView.this.movePoints.get(TrackView.this.movePoints.size() - 1);
                    if (point3.x - point.x > 20 || point3.x - point.x < -20 || point3.y - point.y > 20 || point3.y - point.y < -20) {
                        TrackView.this.movePoints.add(point);
                    }
                }
            }
            return true;
        }
    }

    @Override // android.view.View
    public void draw(Canvas canvas) {
        super.draw(canvas);
        Paint paint = new Paint();
        this.mPaint = paint;
        paint.setColor(-65536);
        this.mPaint.setAntiAlias(true);
        this.mPaint.setStrokeWidth(15.0f);
        this.mPaint.setStrokeCap(Paint.Cap.ROUND);
        if (this.allPoints.size() > 1) {
            Iterator<Point> it = this.allPoints.iterator();
            Point next = null;
            Point next2 = null;
            while (it.hasNext()) {
                if (next == null) {
                    next = it.next();
                } else {
                    if (next2 != null) {
                        next = next2;
                    }
                    next2 = it.next();
                    canvas.drawLine(next.x, next.y, next2.x, next2.y, this.mPaint);
                }
            }
        }
    }

    public void setOnTrackListener(OnTrackListener onTrackListener) {
        this.onTrackListener = onTrackListener;
    }
}
