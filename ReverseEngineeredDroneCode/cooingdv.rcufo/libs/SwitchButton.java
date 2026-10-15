package com.cooingdv.rcufo.libs;

import android.R;
import android.animation.ObjectAnimator;
import android.content.Context;
import android.content.res.ColorStateList;
import android.content.res.TypedArray;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PointF;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Parcel;
import android.os.Parcelable;
import android.text.Layout;
import android.text.StaticLayout;
import android.text.TextPaint;
import android.text.TextUtils;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.ViewParent;
import android.view.animation.AccelerateDecelerateInterpolator;
import android.widget.CompoundButton;
import androidx.core.content.ContextCompat;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.utils.ColorUtils;

/* JADX INFO: loaded from: classes2.dex */
public class SwitchButton extends CompoundButton {
    public static final int DEFAULT_ANIMATION_DURATION = 250;
    public static final float DEFAULT_BACK_MEASURE_RATIO = 1.8f;
    public static final int DEFAULT_TEXT_MARGIN_DP = 2;
    public static final int DEFAULT_THUMB_MARGIN_DP = 2;
    public static final int DEFAULT_THUMB_SIZE_DP = 30;
    public static final int DEFAULT_TINT_COLOR = 3309506;
    private long mAnimationDuration;
    private ColorStateList mBackColor;
    private Drawable mBackDrawable;
    private float mBackMeasureRatio;
    private float mBackRadius;
    private RectF mBackRectF;
    private CompoundButton.OnCheckedChangeListener mChildOnCheckedChangeListener;
    private int mClickTimeout;
    private int mCurrBackColor;
    private int mCurrThumbColor;
    private Drawable mCurrentBackDrawable;
    private boolean mDrawDebugRect;
    private boolean mFadeBack;
    private boolean mIsBackUseDrawable;
    private boolean mIsThumbUseDrawable;
    private float mLastX;
    private int mNextBackColor;
    private Drawable mNextBackDrawable;
    private Layout mOffLayout;
    private int mOffTextColor;
    private Layout mOnLayout;
    private int mOnTextColor;
    private Paint mPaint;
    private RectF mPresentThumbRectF;
    private float mProcess;
    private ObjectAnimator mProcessAnimator;
    private Paint mRectPaint;
    private RectF mSafeRectF;
    private float mStartX;
    private float mStartY;
    private float mTextHeight;
    private float mTextMarginH;
    private CharSequence mTextOff;
    private RectF mTextOffRectF;
    private CharSequence mTextOn;
    private RectF mTextOnRectF;
    private TextPaint mTextPaint;
    private float mTextWidth;
    private ColorStateList mThumbColor;
    private Drawable mThumbDrawable;
    private RectF mThumbMargin;
    private float mThumbRadius;
    private RectF mThumbRectF;
    private PointF mThumbSizeF;
    private int mTintColor;
    private int mTouchSlop;
    private static int[] CHECKED_PRESSED_STATE = {R.attr.state_checked, R.attr.state_enabled, R.attr.state_pressed};
    private static int[] UNCHECKED_PRESSED_STATE = {-16842912, R.attr.state_enabled, R.attr.state_pressed};

    public SwitchButton(Context context, AttributeSet attributeSet, int i) {
        super(context, attributeSet, i);
        this.mDrawDebugRect = false;
        init(attributeSet);
    }

    public SwitchButton(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
        this.mDrawDebugRect = false;
        init(attributeSet);
    }

    public SwitchButton(Context context) {
        super(context);
        this.mDrawDebugRect = false;
        init(null);
    }

    private void init(AttributeSet attributeSet) {
        int i;
        float f;
        float f2;
        String str;
        Drawable drawable;
        ColorStateList colorStateList;
        ColorStateList colorStateList2;
        Drawable drawable2;
        int i2;
        float f3;
        float f4;
        float f5;
        float f6;
        boolean z;
        float fMax;
        float fMax2;
        this.mTouchSlop = ViewConfiguration.get(getContext()).getScaledTouchSlop();
        this.mClickTimeout = ViewConfiguration.getPressedStateDuration() + ViewConfiguration.getTapTimeout();
        this.mPaint = new Paint(1);
        Paint paint = new Paint(1);
        this.mRectPaint = paint;
        paint.setStyle(Paint.Style.STROKE);
        this.mRectPaint.setStrokeWidth(getResources().getDisplayMetrics().density);
        this.mTextPaint = getPaint();
        this.mThumbRectF = new RectF();
        this.mBackRectF = new RectF();
        this.mSafeRectF = new RectF();
        this.mThumbSizeF = new PointF();
        this.mThumbMargin = new RectF();
        this.mTextOnRectF = new RectF();
        this.mTextOffRectF = new RectF();
        ObjectAnimator duration = ObjectAnimator.ofFloat(this, "process", 0.0f, 0.0f).setDuration(250L);
        this.mProcessAnimator = duration;
        duration.setInterpolator(new AccelerateDecelerateInterpolator());
        this.mPresentThumbRectF = new RectF();
        float f7 = getResources().getDisplayMetrics().density;
        float dimension = f7 * 2.0f;
        float fMax3 = f7 * 30.0f;
        float f8 = fMax3 / 2.0f;
        String str2 = null;
        TypedArray typedArrayObtainStyledAttributes = attributeSet == null ? null : getContext().obtainStyledAttributes(attributeSet, C3033R.styleable.SwitchButton);
        if (typedArrayObtainStyledAttributes != null) {
            Drawable drawable3 = typedArrayObtainStyledAttributes.getDrawable(10);
            ColorStateList colorStateList3 = typedArrayObtainStyledAttributes.getColorStateList(9);
            float dimension2 = typedArrayObtainStyledAttributes.getDimension(12, dimension);
            float dimension3 = typedArrayObtainStyledAttributes.getDimension(14, dimension2);
            float dimension4 = typedArrayObtainStyledAttributes.getDimension(15, dimension2);
            float dimension5 = typedArrayObtainStyledAttributes.getDimension(16, dimension2);
            float dimension6 = typedArrayObtainStyledAttributes.getDimension(13, dimension2);
            float dimension7 = typedArrayObtainStyledAttributes.getDimension(18, fMax3);
            float dimension8 = typedArrayObtainStyledAttributes.getDimension(11, fMax3);
            float dimension9 = typedArrayObtainStyledAttributes.getDimension(17, Math.min(dimension7, dimension8) / 2.0f);
            float dimension10 = typedArrayObtainStyledAttributes.getDimension(4, dimension9 + dimension);
            Drawable drawable4 = typedArrayObtainStyledAttributes.getDrawable(2);
            colorStateList2 = typedArrayObtainStyledAttributes.getColorStateList(1);
            float f9 = typedArrayObtainStyledAttributes.getFloat(3, 1.8f);
            int integer = typedArrayObtainStyledAttributes.getInteger(0, 250);
            boolean z2 = typedArrayObtainStyledAttributes.getBoolean(5, true);
            int color = typedArrayObtainStyledAttributes.getColor(19, Integer.MIN_VALUE);
            String string = typedArrayObtainStyledAttributes.getString(8);
            String string2 = typedArrayObtainStyledAttributes.getString(7);
            dimension = typedArrayObtainStyledAttributes.getDimension(6, dimension);
            typedArrayObtainStyledAttributes.recycle();
            fMax2 = dimension8;
            fMax3 = dimension7;
            fMax = f9;
            i = integer;
            z = z2;
            f5 = dimension6;
            f = dimension10;
            f4 = dimension5;
            drawable2 = drawable4;
            f2 = dimension9;
            drawable = drawable3;
            str = string2;
            str2 = string;
            i2 = color;
            colorStateList = colorStateList3;
            f3 = dimension3;
            f6 = dimension4;
        } else {
            i = 250;
            f = f8;
            f2 = f;
            str = null;
            drawable = null;
            colorStateList = null;
            colorStateList2 = null;
            drawable2 = null;
            i2 = Integer.MIN_VALUE;
            f3 = 0.0f;
            f4 = 0.0f;
            f5 = 0.0f;
            f6 = 0.0f;
            z = true;
            fMax = 1.8f;
            fMax2 = fMax3;
        }
        this.mTextOn = str2;
        this.mTextOff = str;
        this.mTextMarginH = dimension;
        this.mThumbDrawable = drawable;
        this.mThumbColor = colorStateList;
        boolean z3 = drawable != null;
        this.mIsThumbUseDrawable = z3;
        this.mTintColor = i2;
        if (i2 == Integer.MIN_VALUE) {
            this.mTintColor = DEFAULT_TINT_COLOR;
        }
        if (!z3 && colorStateList == null) {
            ColorStateList colorStateListGenerateThumbColorWithTintColor = ColorUtils.generateThumbColorWithTintColor(this.mTintColor);
            this.mThumbColor = colorStateListGenerateThumbColorWithTintColor;
            this.mCurrThumbColor = colorStateListGenerateThumbColorWithTintColor.getDefaultColor();
        }
        if (this.mIsThumbUseDrawable) {
            fMax3 = Math.max(fMax3, this.mThumbDrawable.getMinimumWidth());
            fMax2 = Math.max(fMax2, this.mThumbDrawable.getMinimumHeight());
        }
        this.mThumbSizeF.set(fMax3, fMax2);
        this.mBackDrawable = drawable2;
        this.mBackColor = colorStateList2;
        boolean z4 = drawable2 != null;
        this.mIsBackUseDrawable = z4;
        if (!z4 && colorStateList2 == null) {
            ColorStateList colorStateListGenerateBackColorWithTintColor = ColorUtils.generateBackColorWithTintColor(this.mTintColor);
            this.mBackColor = colorStateListGenerateBackColorWithTintColor;
            int defaultColor = colorStateListGenerateBackColorWithTintColor.getDefaultColor();
            this.mCurrBackColor = defaultColor;
            this.mNextBackColor = this.mBackColor.getColorForState(CHECKED_PRESSED_STATE, defaultColor);
        }
        this.mThumbMargin.set(f3, f4, f6, f5);
        if (this.mThumbMargin.width() >= 0.0f) {
            fMax = Math.max(fMax, 1.0f);
        }
        this.mBackMeasureRatio = fMax;
        this.mThumbRadius = f2;
        this.mBackRadius = f;
        long j = i;
        this.mAnimationDuration = j;
        this.mFadeBack = z;
        this.mProcessAnimator.setDuration(j);
        setFocusable(true);
        setClickable(true);
        if (isChecked()) {
            setProcess(1.0f);
        }
    }

    private Layout makeLayout(CharSequence charSequence) {
        TextPaint textPaint = this.mTextPaint;
        return new StaticLayout(charSequence, textPaint, (int) Math.ceil(Layout.getDesiredWidth(charSequence, textPaint)), Layout.Alignment.ALIGN_CENTER, 1.0f, 0.0f, false);
    }

    @Override // android.widget.TextView, android.view.View
    protected void onMeasure(int i, int i2) {
        CharSequence charSequence;
        CharSequence charSequence2;
        if (this.mOnLayout == null && (charSequence2 = this.mTextOn) != null) {
            this.mOnLayout = makeLayout(charSequence2);
        }
        if (this.mOffLayout == null && (charSequence = this.mTextOff) != null) {
            this.mOffLayout = makeLayout(charSequence);
        }
        setMeasuredDimension(measureWidth(i), measureHeight(i2));
    }

    private int measureWidth(int i) {
        int size = View.MeasureSpec.getSize(i);
        int mode = View.MeasureSpec.getMode(i);
        int iCeil = ceil(this.mThumbSizeF.x * this.mBackMeasureRatio);
        if (this.mIsBackUseDrawable) {
            iCeil = Math.max(iCeil, this.mBackDrawable.getMinimumWidth());
        }
        Layout layout = this.mOnLayout;
        float width = layout != null ? layout.getWidth() : 0.0f;
        Layout layout2 = this.mOffLayout;
        float width2 = layout2 != null ? layout2.getWidth() : 0.0f;
        if (width != 0.0f || width2 != 0.0f) {
            this.mTextWidth = Math.max(width, width2) + (this.mTextMarginH * 2.0f);
            float f = iCeil;
            float f2 = f - this.mThumbSizeF.x;
            float f3 = this.mTextWidth;
            if (f2 < f3) {
                iCeil = (int) (f + (f3 - f2));
            }
        }
        int iMax = Math.max(iCeil, ceil(iCeil + this.mThumbMargin.left + this.mThumbMargin.right));
        int iMax2 = Math.max(Math.max(iMax, getPaddingLeft() + iMax + getPaddingRight()), getSuggestedMinimumWidth());
        if (mode == 1073741824) {
            return Math.max(iMax2, size);
        }
        return mode == Integer.MIN_VALUE ? Math.min(iMax2, size) : iMax2;
    }

    private int measureHeight(int i) {
        int mode = View.MeasureSpec.getMode(i);
        int size = View.MeasureSpec.getSize(i);
        int iCeil = ceil(Math.max(this.mThumbSizeF.y, this.mThumbSizeF.y + this.mThumbMargin.top + this.mThumbMargin.right));
        Layout layout = this.mOnLayout;
        float height = layout != null ? layout.getHeight() : 0.0f;
        Layout layout2 = this.mOffLayout;
        float height2 = layout2 != null ? layout2.getHeight() : 0.0f;
        if (height != 0.0f || height2 != 0.0f) {
            float fMax = Math.max(height, height2);
            this.mTextHeight = fMax;
            iCeil = ceil(Math.max(iCeil, fMax));
        }
        int iMax = Math.max(iCeil, getSuggestedMinimumHeight());
        int iMax2 = Math.max(iMax, getPaddingTop() + iMax + getPaddingBottom());
        if (mode == 1073741824) {
            return Math.max(iMax2, size);
        }
        return mode == Integer.MIN_VALUE ? Math.min(iMax2, size) : iMax2;
    }

    @Override // android.view.View
    protected void onSizeChanged(int i, int i2, int i3, int i4) {
        super.onSizeChanged(i, i2, i3, i4);
        if (i == i3 && i2 == i4) {
            return;
        }
        setup();
    }

    private int ceil(double d) {
        return (int) Math.ceil(d);
    }

    private void setup() {
        float paddingTop = getPaddingTop() + Math.max(0.0f, this.mThumbMargin.top);
        float paddingLeft = getPaddingLeft() + Math.max(0.0f, this.mThumbMargin.left);
        if (this.mOnLayout != null && this.mOffLayout != null && this.mThumbMargin.top + this.mThumbMargin.bottom > 0.0f) {
            paddingTop += (((((getMeasuredHeight() - getPaddingBottom()) - getPaddingTop()) - this.mThumbSizeF.y) - this.mThumbMargin.top) - this.mThumbMargin.bottom) / 2.0f;
        }
        if (this.mIsThumbUseDrawable) {
            PointF pointF = this.mThumbSizeF;
            pointF.x = Math.max(pointF.x, this.mThumbDrawable.getMinimumWidth());
            PointF pointF2 = this.mThumbSizeF;
            pointF2.y = Math.max(pointF2.y, this.mThumbDrawable.getMinimumHeight());
        }
        this.mThumbRectF.set(paddingLeft, paddingTop, this.mThumbSizeF.x + paddingLeft, this.mThumbSizeF.y + paddingTop);
        float f = this.mThumbRectF.left - this.mThumbMargin.left;
        float fMin = Math.min(0.0f, ((Math.max(this.mThumbSizeF.x * this.mBackMeasureRatio, this.mThumbSizeF.x + this.mTextWidth) - this.mThumbRectF.width()) - this.mTextWidth) / 2.0f);
        float fMin2 = Math.min(0.0f, (((this.mThumbRectF.height() + this.mThumbMargin.top) + this.mThumbMargin.bottom) - this.mTextHeight) / 2.0f);
        this.mBackRectF.set(f + fMin, (this.mThumbRectF.top - this.mThumbMargin.top) + fMin2, (((f + this.mThumbMargin.left) + Math.max(this.mThumbSizeF.x * this.mBackMeasureRatio, this.mThumbSizeF.x + this.mTextWidth)) + this.mThumbMargin.right) - fMin, (this.mThumbRectF.bottom + this.mThumbMargin.bottom) - fMin2);
        this.mSafeRectF.set(this.mThumbRectF.left, 0.0f, (this.mBackRectF.right - this.mThumbMargin.right) - this.mThumbRectF.width(), 0.0f);
        this.mBackRadius = Math.min(Math.min(this.mBackRectF.width(), this.mBackRectF.height()) / 2.0f, this.mBackRadius);
        Drawable drawable = this.mBackDrawable;
        if (drawable != null) {
            drawable.setBounds((int) this.mBackRectF.left, (int) this.mBackRectF.top, ceil(this.mBackRectF.right), ceil(this.mBackRectF.bottom));
        }
        if (this.mOnLayout != null) {
            float fWidth = ((this.mBackRectF.left + (((this.mBackRectF.width() - this.mThumbRectF.width()) - this.mOnLayout.getWidth()) / 2.0f)) - this.mThumbMargin.left) + (this.mTextMarginH * (this.mThumbMargin.left > 0.0f ? 1 : -1));
            float fHeight = this.mBackRectF.top + ((this.mBackRectF.height() - this.mOnLayout.getHeight()) / 2.0f);
            this.mTextOnRectF.set(fWidth, fHeight, this.mOnLayout.getWidth() + fWidth, this.mOnLayout.getHeight() + fHeight);
        }
        if (this.mOffLayout != null) {
            float fWidth2 = (((this.mBackRectF.right - (((this.mBackRectF.width() - this.mThumbRectF.width()) - this.mOffLayout.getWidth()) / 2.0f)) + this.mThumbMargin.right) - this.mOffLayout.getWidth()) - (this.mTextMarginH * (this.mThumbMargin.right <= 0.0f ? -1 : 1));
            float fHeight2 = this.mBackRectF.top + ((this.mBackRectF.height() - this.mOffLayout.getHeight()) / 2.0f);
            this.mTextOffRectF.set(fWidth2, fHeight2, this.mOffLayout.getWidth() + fWidth2, this.mOffLayout.getHeight() + fHeight2);
        }
    }

    /* JADX WARN: Code duplicated, block: B:45:0x0125  */
    /* JADX WARN: Code duplicated, block: B:46:0x0128  */
    @Override // android.widget.CompoundButton, android.widget.TextView, android.view.View
    protected void onDraw(Canvas canvas) {
        float f;
        float process;
        int i;
        super.onDraw(canvas);
        float process2 = 1.0f;
        if (this.mIsBackUseDrawable) {
            if (this.mFadeBack && this.mCurrentBackDrawable != null && this.mNextBackDrawable != null) {
                int process3 = (int) ((isChecked() ? getProcess() : 1.0f - getProcess()) * 255.0f);
                this.mCurrentBackDrawable.setAlpha(process3);
                this.mCurrentBackDrawable.draw(canvas);
                this.mNextBackDrawable.setAlpha(255 - process3);
                this.mNextBackDrawable.draw(canvas);
            } else {
                this.mBackDrawable.setAlpha(255);
                this.mBackDrawable.draw(canvas);
            }
        } else if (this.mFadeBack) {
            int process4 = (int) ((isChecked() ? getProcess() : 1.0f - getProcess()) * 255.0f);
            this.mPaint.setARGB((Color.alpha(this.mCurrBackColor) * process4) / 255, Color.red(this.mCurrBackColor), Color.green(this.mCurrBackColor), Color.blue(this.mCurrBackColor));
            RectF rectF = this.mBackRectF;
            float f2 = this.mBackRadius;
            canvas.drawRoundRect(rectF, f2, f2, this.mPaint);
            this.mPaint.setARGB((Color.alpha(this.mNextBackColor) * (255 - process4)) / 255, Color.red(this.mNextBackColor), Color.green(this.mNextBackColor), Color.blue(this.mNextBackColor));
            RectF rectF2 = this.mBackRectF;
            float f3 = this.mBackRadius;
            canvas.drawRoundRect(rectF2, f3, f3, this.mPaint);
            this.mPaint.setAlpha(255);
        } else {
            this.mPaint.setColor(this.mCurrBackColor);
            RectF rectF3 = this.mBackRectF;
            float f4 = this.mBackRadius;
            canvas.drawRoundRect(rectF3, f4, f4, this.mPaint);
        }
        Layout layout = ((double) getProcess()) > 0.5d ? this.mOnLayout : this.mOffLayout;
        RectF rectF4 = ((double) getProcess()) > 0.5d ? this.mTextOnRectF : this.mTextOffRectF;
        if (layout != null && rectF4 != null) {
            if (getProcess() >= 0.75d) {
                process2 = getProcess() * 4.0f;
                process = 3.0f;
            } else {
                if (getProcess() < 0.25d) {
                    process = getProcess() * 4.0f;
                } else {
                    f = 0.0f;
                }
                int i2 = (int) (f * 255.0f);
                if (getProcess() > 0.5d) {
                    i = this.mOnTextColor;
                } else {
                    i = this.mOffTextColor;
                }
                layout.getPaint().setARGB((Color.alpha(i) * i2) / 255, Color.red(i), Color.green(i), Color.blue(i));
                canvas.save();
                canvas.translate(rectF4.left, rectF4.top);
                layout.draw(canvas);
                canvas.restore();
            }
            f = process2 - process;
            int i3 = (int) (f * 255.0f);
            if (getProcess() > 0.5d) {
                i = this.mOnTextColor;
            } else {
                i = this.mOffTextColor;
            }
            layout.getPaint().setARGB((Color.alpha(i) * i3) / 255, Color.red(i), Color.green(i), Color.blue(i));
            canvas.save();
            canvas.translate(rectF4.left, rectF4.top);
            layout.draw(canvas);
            canvas.restore();
        }
        this.mPresentThumbRectF.set(this.mThumbRectF);
        this.mPresentThumbRectF.offset(this.mProcess * this.mSafeRectF.width(), 0.0f);
        if (this.mIsThumbUseDrawable) {
            this.mThumbDrawable.setBounds((int) this.mPresentThumbRectF.left, (int) this.mPresentThumbRectF.top, ceil(this.mPresentThumbRectF.right), ceil(this.mPresentThumbRectF.bottom));
            this.mThumbDrawable.draw(canvas);
        } else {
            this.mPaint.setColor(this.mCurrThumbColor);
            RectF rectF5 = this.mPresentThumbRectF;
            float f5 = this.mThumbRadius;
            canvas.drawRoundRect(rectF5, f5, f5, this.mPaint);
        }
        if (this.mDrawDebugRect) {
            this.mRectPaint.setColor(Color.parseColor("#AA0000"));
            canvas.drawRect(this.mBackRectF, this.mRectPaint);
            this.mRectPaint.setColor(Color.parseColor("#0000FF"));
            canvas.drawRect(this.mPresentThumbRectF, this.mRectPaint);
            this.mRectPaint.setColor(Color.parseColor("#00CC00"));
            canvas.drawRect(((double) getProcess()) > 0.5d ? this.mTextOnRectF : this.mTextOffRectF, this.mRectPaint);
        }
    }

    @Override // android.widget.CompoundButton, android.widget.TextView, android.view.View
    protected void drawableStateChanged() {
        ColorStateList colorStateList;
        ColorStateList colorStateList2;
        super.drawableStateChanged();
        if (!this.mIsThumbUseDrawable && (colorStateList2 = this.mThumbColor) != null) {
            this.mCurrThumbColor = colorStateList2.getColorForState(getDrawableState(), this.mCurrThumbColor);
        } else {
            setDrawableState(this.mThumbDrawable);
        }
        int[] iArr = isChecked() ? UNCHECKED_PRESSED_STATE : CHECKED_PRESSED_STATE;
        ColorStateList textColors = getTextColors();
        if (textColors != null) {
            int defaultColor = textColors.getDefaultColor();
            this.mOnTextColor = textColors.getColorForState(CHECKED_PRESSED_STATE, defaultColor);
            this.mOffTextColor = textColors.getColorForState(UNCHECKED_PRESSED_STATE, defaultColor);
        }
        if (!this.mIsBackUseDrawable && (colorStateList = this.mBackColor) != null) {
            int colorForState = colorStateList.getColorForState(getDrawableState(), this.mCurrBackColor);
            this.mCurrBackColor = colorForState;
            this.mNextBackColor = this.mBackColor.getColorForState(iArr, colorForState);
            return;
        }
        Drawable drawable = this.mBackDrawable;
        if ((drawable instanceof StateListDrawable) && this.mFadeBack) {
            drawable.setState(iArr);
            this.mNextBackDrawable = this.mBackDrawable.getCurrent().mutate();
        } else {
            this.mNextBackDrawable = null;
        }
        setDrawableState(this.mBackDrawable);
        Drawable drawable2 = this.mBackDrawable;
        if (drawable2 != null) {
            this.mCurrentBackDrawable = drawable2.getCurrent().mutate();
        }
    }

    /* JADX WARN: Code duplicated, block: B:16:0x0047  */
    /* JADX WARN: Code duplicated, block: B:23:0x006f  */
    /* JADX WARN: Code duplicated, block: B:25:0x0075  */
    /* JADX WARN: Code duplicated, block: B:26:0x007c  */
    @Override // android.widget.TextView, android.view.View
    public boolean onTouchEvent(MotionEvent motionEvent) {
        boolean statusBasedOnPos;
        int i;
        if (!isEnabled() || !isClickable()) {
            return false;
        }
        int action = motionEvent.getAction();
        float x = motionEvent.getX() - this.mStartX;
        float y = motionEvent.getY() - this.mStartY;
        if (action == 0) {
            catchView();
            this.mStartX = motionEvent.getX();
            this.mStartY = motionEvent.getY();
            this.mLastX = this.mStartX;
            setPressed(true);
        } else if (action == 1) {
            setPressed(false);
            statusBasedOnPos = getStatusBasedOnPos();
            float eventTime = motionEvent.getEventTime() - motionEvent.getDownTime();
            i = this.mTouchSlop;
            if (x >= i && y < i && eventTime < this.mClickTimeout) {
                performClick();
            } else if (statusBasedOnPos != isChecked()) {
                playSoundEffect(0);
                setChecked(statusBasedOnPos);
            } else {
                animateToState(statusBasedOnPos);
            }
        } else if (action == 2) {
            float x2 = motionEvent.getX();
            setProcess(getProcess() + ((x2 - this.mLastX) / this.mSafeRectF.width()));
            this.mLastX = x2;
        } else if (action == 3) {
            setPressed(false);
            statusBasedOnPos = getStatusBasedOnPos();
            float eventTime2 = motionEvent.getEventTime() - motionEvent.getDownTime();
            i = this.mTouchSlop;
            if (x >= i) {
                if (statusBasedOnPos != isChecked()) {
                    playSoundEffect(0);
                    setChecked(statusBasedOnPos);
                } else {
                    animateToState(statusBasedOnPos);
                }
            } else if (statusBasedOnPos != isChecked()) {
                playSoundEffect(0);
                setChecked(statusBasedOnPos);
            } else {
                animateToState(statusBasedOnPos);
            }
        }
        return true;
    }

    private boolean getStatusBasedOnPos() {
        return getProcess() > 0.5f;
    }

    public final float getProcess() {
        return this.mProcess;
    }

    /* JADX WARN: Code duplicated, block: B:4:0x0006 A[PHI: r0
      0x0006: PHI (r0v2 float) = (r0v0 float), (r0v1 float) binds: [B:3:0x0004, B:6:0x000b] A[DONT_GENERATE, DONT_INLINE]] */
    public final void setProcess(float f) {
        float f2 = 1.0f;
        if (f > 1.0f) {
            f = f2;
        } else {
            f2 = 0.0f;
            if (f < 0.0f) {
                f = f2;
            }
        }
        this.mProcess = f;
        invalidate();
    }

    @Override // android.widget.CompoundButton, android.view.View
    public boolean performClick() {
        return super.performClick();
    }

    protected void animateToState(boolean z) {
        ObjectAnimator objectAnimator = this.mProcessAnimator;
        if (objectAnimator == null) {
            return;
        }
        if (objectAnimator.isRunning()) {
            this.mProcessAnimator.cancel();
        }
        this.mProcessAnimator.setDuration(this.mAnimationDuration);
        if (z) {
            this.mProcessAnimator.setFloatValues(this.mProcess, 1.0f);
        } else {
            this.mProcessAnimator.setFloatValues(this.mProcess, 0.0f);
        }
        this.mProcessAnimator.start();
    }

    private void catchView() {
        ViewParent parent = getParent();
        if (parent != null) {
            parent.requestDisallowInterceptTouchEvent(true);
        }
    }

    @Override // android.widget.CompoundButton, android.widget.Checkable
    public void setChecked(boolean z) {
        if (isChecked() != z) {
            animateToState(z);
        }
        super.setChecked(z);
    }

    public void setCheckedNoEvent(boolean z) {
        if (this.mChildOnCheckedChangeListener == null) {
            setChecked(z);
            return;
        }
        super.setOnCheckedChangeListener(null);
        setChecked(z);
        setOnCheckedChangeListener(this.mChildOnCheckedChangeListener);
    }

    public void setCheckedImmediatelyNoEvent(boolean z) {
        if (this.mChildOnCheckedChangeListener == null) {
            setCheckedImmediately(z);
            return;
        }
        super.setOnCheckedChangeListener(null);
        setCheckedImmediately(z);
        setOnCheckedChangeListener(this.mChildOnCheckedChangeListener);
    }

    public void toggleNoEvent() {
        if (this.mChildOnCheckedChangeListener == null) {
            toggle();
            return;
        }
        super.setOnCheckedChangeListener(null);
        toggle();
        setOnCheckedChangeListener(this.mChildOnCheckedChangeListener);
    }

    public void toggleImmediatelyNoEvent() {
        if (this.mChildOnCheckedChangeListener == null) {
            toggleImmediately();
            return;
        }
        super.setOnCheckedChangeListener(null);
        toggleImmediately();
        setOnCheckedChangeListener(this.mChildOnCheckedChangeListener);
    }

    @Override // android.widget.CompoundButton
    public void setOnCheckedChangeListener(CompoundButton.OnCheckedChangeListener onCheckedChangeListener) {
        super.setOnCheckedChangeListener(onCheckedChangeListener);
        this.mChildOnCheckedChangeListener = onCheckedChangeListener;
    }

    public void setCheckedImmediately(boolean z) {
        super.setChecked(z);
        ObjectAnimator objectAnimator = this.mProcessAnimator;
        if (objectAnimator != null && objectAnimator.isRunning()) {
            this.mProcessAnimator.cancel();
        }
        setProcess(z ? 1.0f : 0.0f);
        invalidate();
    }

    public void toggleImmediately() {
        setCheckedImmediately(!isChecked());
    }

    private void setDrawableState(Drawable drawable) {
        if (drawable != null) {
            drawable.setState(getDrawableState());
            invalidate();
        }
    }

    public boolean isDrawDebugRect() {
        return this.mDrawDebugRect;
    }

    public void setDrawDebugRect(boolean z) {
        this.mDrawDebugRect = z;
        invalidate();
    }

    public long getAnimationDuration() {
        return this.mAnimationDuration;
    }

    public void setAnimationDuration(long j) {
        this.mAnimationDuration = j;
    }

    public Drawable getThumbDrawable() {
        return this.mThumbDrawable;
    }

    public void setThumbDrawable(Drawable drawable) {
        this.mThumbDrawable = drawable;
        this.mIsThumbUseDrawable = drawable != null;
        setup();
        refreshDrawableState();
        requestLayout();
        invalidate();
    }

    public void setThumbDrawableRes(int i) {
        setThumbDrawable(ContextCompat.getDrawable(getContext(), i));
    }

    public Drawable getBackDrawable() {
        return this.mBackDrawable;
    }

    public void setBackDrawable(Drawable drawable) {
        this.mBackDrawable = drawable;
        this.mIsBackUseDrawable = drawable != null;
        setup();
        refreshDrawableState();
        requestLayout();
        invalidate();
    }

    public void setBackDrawableRes(int i) {
        setBackDrawable(ContextCompat.getDrawable(getContext(), i));
    }

    public ColorStateList getBackColor() {
        return this.mBackColor;
    }

    public void setBackColor(ColorStateList colorStateList) {
        this.mBackColor = colorStateList;
        if (colorStateList != null) {
            setBackDrawable(null);
        }
        invalidate();
    }

    public ColorStateList getThumbColor() {
        return this.mThumbColor;
    }

    public void setThumbColor(ColorStateList colorStateList) {
        this.mThumbColor = colorStateList;
        if (colorStateList != null) {
            setThumbDrawable(null);
        }
    }

    public float getBackMeasureRatio() {
        return this.mBackMeasureRatio;
    }

    public void setBackMeasureRatio(float f) {
        this.mBackMeasureRatio = f;
        requestLayout();
    }

    public RectF getThumbMargin() {
        return this.mThumbMargin;
    }

    public void setThumbMargin(RectF rectF) {
        if (rectF == null) {
            setThumbMargin(0.0f, 0.0f, 0.0f, 0.0f);
        } else {
            setThumbMargin(rectF.left, rectF.top, rectF.right, rectF.bottom);
        }
    }

    public void setThumbMargin(float f, float f2, float f3, float f4) {
        this.mThumbMargin.set(f, f2, f3, f4);
        requestLayout();
    }

    public void setThumbSize(float f, float f2) {
        this.mThumbSizeF.set(f, f2);
        setup();
        requestLayout();
    }

    public float getThumbWidth() {
        return this.mThumbSizeF.x;
    }

    public float getThumbHeight() {
        return this.mThumbSizeF.y;
    }

    public void setThumbSize(PointF pointF) {
        if (pointF == null) {
            float f = getResources().getDisplayMetrics().density * 30.0f;
            setThumbSize(f, f);
        } else {
            setThumbSize(pointF.x, pointF.y);
        }
    }

    public PointF getThumbSizeF() {
        return this.mThumbSizeF;
    }

    public float getThumbRadius() {
        return this.mThumbRadius;
    }

    public void setThumbRadius(float f) {
        this.mThumbRadius = f;
        if (this.mIsThumbUseDrawable) {
            return;
        }
        invalidate();
    }

    public PointF getBackSizeF() {
        return new PointF(this.mBackRectF.width(), this.mBackRectF.height());
    }

    public float getBackRadius() {
        return this.mBackRadius;
    }

    public void setBackRadius(float f) {
        this.mBackRadius = f;
        if (this.mIsBackUseDrawable) {
            return;
        }
        invalidate();
    }

    public boolean isFadeBack() {
        return this.mFadeBack;
    }

    public void setFadeBack(boolean z) {
        this.mFadeBack = z;
    }

    public int getTintColor() {
        return this.mTintColor;
    }

    public void setTintColor(int i) {
        this.mTintColor = i;
        this.mThumbColor = ColorUtils.generateThumbColorWithTintColor(i);
        this.mBackColor = ColorUtils.generateBackColorWithTintColor(this.mTintColor);
        this.mIsBackUseDrawable = false;
        this.mIsThumbUseDrawable = false;
        refreshDrawableState();
        invalidate();
    }

    public void setText(CharSequence charSequence, CharSequence charSequence2) {
        this.mTextOn = charSequence;
        this.mTextOff = charSequence2;
        this.mOnLayout = null;
        this.mOffLayout = null;
        requestLayout();
    }

    @Override // android.widget.CompoundButton, android.widget.TextView, android.view.View
    public Parcelable onSaveInstanceState() {
        SavedState savedState = new SavedState(super.onSaveInstanceState());
        savedState.onText = this.mTextOn;
        savedState.offText = this.mTextOff;
        return savedState;
    }

    @Override // android.widget.CompoundButton, android.widget.TextView, android.view.View
    public void onRestoreInstanceState(Parcelable parcelable) {
        SavedState savedState = (SavedState) parcelable;
        setText(savedState.onText, savedState.offText);
        super.onRestoreInstanceState(savedState.getSuperState());
    }

    static class SavedState extends View.BaseSavedState {
        public static final Parcelable.Creator<SavedState> CREATOR = new Parcelable.Creator<SavedState>() { // from class: com.cooingdv.rcufo.libs.SwitchButton.SavedState.1
            /* JADX WARN: Can't rename method to resolve collision */
            @Override // android.os.Parcelable.Creator
            public SavedState createFromParcel(Parcel parcel) {
                return new SavedState(parcel);
            }

            /* JADX WARN: Can't rename method to resolve collision */
            @Override // android.os.Parcelable.Creator
            public SavedState[] newArray(int i) {
                return new SavedState[i];
            }
        };
        CharSequence offText;
        CharSequence onText;

        SavedState(Parcelable parcelable) {
            super(parcelable);
        }

        private SavedState(Parcel parcel) {
            super(parcel);
            this.onText = (CharSequence) TextUtils.CHAR_SEQUENCE_CREATOR.createFromParcel(parcel);
            this.offText = (CharSequence) TextUtils.CHAR_SEQUENCE_CREATOR.createFromParcel(parcel);
        }

        @Override // android.view.View.BaseSavedState, android.view.AbsSavedState, android.os.Parcelable
        public void writeToParcel(Parcel parcel, int i) {
            super.writeToParcel(parcel, i);
            TextUtils.writeToParcel(this.onText, parcel, i);
            TextUtils.writeToParcel(this.offText, parcel, i);
        }
    }
}
