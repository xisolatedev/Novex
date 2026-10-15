package com.cooingdv.rcufo.libs.verticalseekbar;

import android.content.Context;
import android.content.res.TypedArray;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.util.AttributeSet;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.widget.ProgressBar;
import androidx.appcompat.widget.AppCompatSeekBar;
import androidx.core.view.ViewCompat;
import com.cooingdv.rcufo.C3033R;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/* JADX INFO: loaded from: classes2.dex */
public class VerticalSeekBar extends AppCompatSeekBar {
    public static final int ROTATION_ANGLE_CW_270 = 270;
    public static final int ROTATION_ANGLE_CW_90 = 90;
    private boolean mIsDragging;
    private Method mMethodSetProgressFromUser;
    private int mRotationAngle;
    private Drawable mThumb_;

    private static boolean isValidRotationAngle(int i) {
        return i == 90 || i == 270;
    }

    public VerticalSeekBar(Context context) {
        super(context);
        this.mRotationAngle = 90;
        initialize(context, null, 0, 0);
    }

    public VerticalSeekBar(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
        this.mRotationAngle = 90;
        initialize(context, attributeSet, 0, 0);
    }

    public VerticalSeekBar(Context context, AttributeSet attributeSet, int i) {
        super(context, attributeSet, i);
        this.mRotationAngle = 90;
        initialize(context, attributeSet, i, 0);
    }

    private void initialize(Context context, AttributeSet attributeSet, int i, int i2) {
        ViewCompat.setLayoutDirection(this, 0);
        if (attributeSet != null) {
            TypedArray typedArrayObtainStyledAttributes = context.obtainStyledAttributes(attributeSet, C3033R.styleable.VerticalSeekBar, i, i2);
            int integer = typedArrayObtainStyledAttributes.getInteger(0, 0);
            if (isValidRotationAngle(integer)) {
                this.mRotationAngle = integer;
            }
            typedArrayObtainStyledAttributes.recycle();
        }
    }

    @Override // android.widget.AbsSeekBar
    public void setThumb(Drawable drawable) {
        this.mThumb_ = drawable;
        super.setThumb(drawable);
    }

    @Override // android.widget.AbsSeekBar, android.view.View
    public boolean onTouchEvent(MotionEvent motionEvent) {
        if (useViewRotation()) {
            return onTouchEventUseViewRotation(motionEvent);
        }
        return onTouchEventTraditionalRotation(motionEvent);
    }

    private boolean onTouchEventTraditionalRotation(MotionEvent motionEvent) {
        if (!isEnabled()) {
            return false;
        }
        int action = motionEvent.getAction();
        if (action == 0) {
            setPressed(true);
            onStartTrackingTouch();
            trackTouchEvent(motionEvent);
            attemptClaimDrag(true);
            invalidate();
        } else if (action == 1) {
            if (this.mIsDragging) {
                trackTouchEvent(motionEvent);
                onStopTrackingTouch();
                setPressed(false);
            } else {
                onStartTrackingTouch();
                trackTouchEvent(motionEvent);
                onStopTrackingTouch();
                attemptClaimDrag(false);
            }
            invalidate();
        } else if (action != 2) {
            if (action == 3) {
                if (this.mIsDragging) {
                    onStopTrackingTouch();
                    setPressed(false);
                }
                invalidate();
            }
        } else if (this.mIsDragging) {
            trackTouchEvent(motionEvent);
        }
        return true;
    }

    private boolean onTouchEventUseViewRotation(MotionEvent motionEvent) {
        boolean zOnTouchEvent = super.onTouchEvent(motionEvent);
        if (zOnTouchEvent) {
            int action = motionEvent.getAction();
            if (action == 0) {
                attemptClaimDrag(true);
            } else if (action == 1 || action == 3) {
                attemptClaimDrag(false);
            }
        }
        return zOnTouchEvent;
    }

    private void trackTouchEvent(MotionEvent motionEvent) {
        float f;
        int paddingLeft = super.getPaddingLeft();
        int paddingRight = super.getPaddingRight();
        int height = getHeight() - paddingLeft;
        int i = height - paddingRight;
        int y = (int) motionEvent.getY();
        int i2 = this.mRotationAngle;
        float f2 = 0.0f;
        if (i2 != 90) {
            f = i2 != 270 ? 0.0f : height - y;
        } else {
            f = y - paddingLeft;
        }
        if (f >= 0.0f && i != 0) {
            float f3 = i;
            f2 = f > f3 ? 1.0f : f / f3;
        }
        _setProgressFromUser((int) (f2 * getMax()), true);
    }

    private void attemptClaimDrag(boolean z) {
        ViewParent parent = getParent();
        if (parent != null) {
            parent.requestDisallowInterceptTouchEvent(z);
        }
    }

    private void onStartTrackingTouch() {
        this.mIsDragging = true;
    }

    private void onStopTrackingTouch() {
        this.mIsDragging = false;
    }

    /* JADX WARN: Code duplicated, block: B:13:0x001c  */
    /* JADX WARN: Code duplicated, block: B:16:0x0020  */
    /* JADX WARN: Code duplicated, block: B:18:0x002c  */
    @Override // android.widget.AbsSeekBar, android.view.View, android.view.KeyEvent.Callback
    public boolean onKeyDown(int i, KeyEvent keyEvent) {
        int progress;
        if (isEnabled()) {
            int i2 = -1;
            boolean z = false;
            switch (i) {
                case 19:
                    if (this.mRotationAngle == 270) {
                        i2 = 1;
                    }
                    z = true;
                    if (z) {
                        progress = getProgress() + (i2 * getKeyProgressIncrement());
                        if (progress >= 0 && progress <= getMax()) {
                            _setProgressFromUser(progress, true);
                        }
                        return true;
                    }
                    break;
                case 20:
                    if (this.mRotationAngle == 90) {
                        i2 = 1;
                    }
                    z = true;
                    if (z) {
                        progress = getProgress() + (i2 * getKeyProgressIncrement());
                        if (progress >= 0) {
                            _setProgressFromUser(progress, true);
                        }
                        return true;
                    }
                    break;
                case 21:
                case 22:
                    return false;
                default:
                    i2 = 0;
                    if (z) {
                        progress = getProgress() + (i2 * getKeyProgressIncrement());
                        if (progress >= 0) {
                            _setProgressFromUser(progress, true);
                        }
                        return true;
                    }
                    break;
            }
        }
        return super.onKeyDown(i, keyEvent);
    }

    @Override // android.widget.ProgressBar
    public synchronized void setProgress(int i) {
        super.setProgress(i);
        if (!useViewRotation()) {
            refreshThumb();
        }
    }

    private synchronized void _setProgressFromUser(int i, boolean z) {
        if (this.mMethodSetProgressFromUser == null) {
            try {
                Method declaredMethod = ProgressBar.class.getDeclaredMethod("setProgress", Integer.TYPE, Boolean.TYPE);
                declaredMethod.setAccessible(true);
                this.mMethodSetProgressFromUser = declaredMethod;
            } catch (NoSuchMethodException unused) {
            }
        }
        Method method = this.mMethodSetProgressFromUser;
        if (method != null) {
            try {
                method.invoke(this, Integer.valueOf(i), Boolean.valueOf(z));
            } catch (IllegalAccessException | IllegalArgumentException | InvocationTargetException unused2) {
            }
        } else {
            super.setProgress(i);
        }
        refreshThumb();
    }

    @Override // android.widget.AbsSeekBar, android.widget.ProgressBar, android.view.View
    protected synchronized void onMeasure(int i, int i2) {
        if (useViewRotation()) {
            super.onMeasure(i, i2);
        } else {
            super.onMeasure(i2, i);
            ViewGroup.LayoutParams layoutParams = getLayoutParams();
            if (isInEditMode() && layoutParams != null && layoutParams.height >= 0) {
                setMeasuredDimension(super.getMeasuredHeight(), layoutParams.height);
            } else {
                setMeasuredDimension(super.getMeasuredHeight(), super.getMeasuredWidth());
            }
        }
    }

    @Override // android.widget.AbsSeekBar, android.widget.ProgressBar, android.view.View
    protected void onSizeChanged(int i, int i2, int i3, int i4) {
        if (useViewRotation()) {
            super.onSizeChanged(i, i2, i3, i4);
        } else {
            super.onSizeChanged(i2, i, i4, i3);
        }
    }

    @Override // androidx.appcompat.widget.AppCompatSeekBar, android.widget.AbsSeekBar, android.widget.ProgressBar, android.view.View
    protected synchronized void onDraw(Canvas canvas) {
        if (!useViewRotation()) {
            int i = this.mRotationAngle;
            if (i == 90) {
                canvas.rotate(90.0f);
                canvas.translate(0.0f, -super.getWidth());
            } else if (i == 270) {
                canvas.rotate(-90.0f);
                canvas.translate(-super.getHeight(), 0.0f);
            }
        }
        super.onDraw(canvas);
    }

    public int getRotationAngle() {
        return this.mRotationAngle;
    }

    public void setRotationAngle(int i) {
        if (!isValidRotationAngle(i)) {
            throw new IllegalArgumentException("Invalid angle specified :" + i);
        }
        if (this.mRotationAngle == i) {
            return;
        }
        this.mRotationAngle = i;
        if (useViewRotation()) {
            VerticalSeekBarWrapper wrapper = getWrapper();
            if (wrapper != null) {
                wrapper.applyViewRotation();
                return;
            }
            return;
        }
        requestLayout();
    }

    private void refreshThumb() {
        onSizeChanged(super.getWidth(), super.getHeight(), 0, 0);
    }

    boolean useViewRotation() {
        return !isInEditMode();
    }

    private VerticalSeekBarWrapper getWrapper() {
        ViewParent parent = getParent();
        if (parent instanceof VerticalSeekBarWrapper) {
            return (VerticalSeekBarWrapper) parent;
        }
        return null;
    }
}
