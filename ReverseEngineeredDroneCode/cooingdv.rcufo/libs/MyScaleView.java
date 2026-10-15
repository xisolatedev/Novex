package com.cooingdv.rcufo.libs;

import android.content.Context;
import android.content.res.TypedArray;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.util.AttributeSet;
import android.view.View;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.utils.AppUtils;

/* JADX INFO: loaded from: classes2.dex */
public class MyScaleView extends View {
    private final int HORIZONTAL;
    private final int VERTICAL;
    private Bitmap bitmap;
    private Paint bluePaint;
    private Context context;
    private int currentValue;
    private int cursorHalfWidth;
    private float gap;
    private float largeHeight;
    private int maxValue;
    private int orientation;
    private float smallHeight;
    private float startX;
    private float startY;
    private Paint whitePaint;
    private float yLenght;
    private Paint yellowPaint;

    public MyScaleView(Context context) {
        super(context);
        this.HORIZONTAL = 0;
        this.VERTICAL = 1;
        this.maxValue = 24;
        this.gap = 8.0f;
        this.smallHeight = 10.0f;
        this.largeHeight = 24.0f;
        this.currentValue = 12;
        this.cursorHalfWidth = 5;
        this.context = context;
        init(null);
    }

    public MyScaleView(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
        this.HORIZONTAL = 0;
        this.VERTICAL = 1;
        this.maxValue = 24;
        this.gap = 8.0f;
        this.smallHeight = 10.0f;
        this.largeHeight = 24.0f;
        this.currentValue = 12;
        this.cursorHalfWidth = 5;
        this.context = context;
        init(attributeSet);
    }

    private void init(AttributeSet attributeSet) {
        this.cursorHalfWidth = AppUtils.dip2px(this.context, this.cursorHalfWidth);
        TypedArray typedArrayObtainStyledAttributes = this.context.obtainStyledAttributes(attributeSet, C3033R.styleable.MyScaleView);
        this.orientation = typedArrayObtainStyledAttributes.getInt(0, 0);
        this.gap = typedArrayObtainStyledAttributes.getFloat(1, AppUtils.dip2px(this.context, 8.0f));
        typedArrayObtainStyledAttributes.recycle();
        Paint paint = new Paint(1);
        this.whitePaint = paint;
        paint.setStyle(Paint.Style.FILL);
        this.whitePaint.setStrokeWidth(2.0f);
        this.whitePaint.setColor(getResources().getColor(C3033R.color.text_white));
        Paint paint2 = new Paint(1);
        this.bluePaint = paint2;
        paint2.setStyle(Paint.Style.FILL);
        this.bluePaint.setStrokeWidth(2.0f);
        this.bluePaint.setColor(getResources().getColor(C3033R.color.text_blue));
        Paint paint3 = new Paint(1);
        this.yellowPaint = paint3;
        paint3.setStyle(Paint.Style.FILL);
        this.yellowPaint.setStrokeWidth(4.0f);
        this.yellowPaint.setColor(Color.argb(255, 85, 158, 201));
        this.yLenght = AppUtils.dip2px(this.context, this.smallHeight);
        if (this.orientation == 0) {
            this.bitmap = BitmapFactory.decodeResource(getResources(), C3033R.mipmap.icon_seekbar_center);
        } else {
            this.bitmap = BitmapFactory.decodeResource(getResources(), C3033R.mipmap.icon_seekbar_center_vertical);
        }
    }

    @Override // android.view.View
    protected void onMeasure(int i, int i2) {
        super.onMeasure(i, i2);
    }

    @Override // android.view.View
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int i = 0;
        if (this.orientation == 0) {
            this.startY = (getHeight() / 2) - (this.largeHeight / 2.0f);
            this.startX = this.cursorHalfWidth * 2;
            this.gap = (getWidth() - (this.cursorHalfWidth * 3)) / this.maxValue;
            while (i <= this.maxValue) {
                if (i == 8) {
                    this.yLenght = AppUtils.dip2px(this.context, this.largeHeight);
                } else {
                    this.yLenght = AppUtils.dip2px(this.context, this.smallHeight);
                }
                i++;
            }
            canvas.drawBitmap(this.bitmap, (this.currentValue * this.gap) - this.cursorHalfWidth, this.startY - (AppUtils.dip2px(this.context, this.largeHeight) / 3), this.yellowPaint);
            return;
        }
        this.startY = this.cursorHalfWidth;
        this.startX = (getWidth() / 2) - (this.largeHeight / 2.0f);
        this.gap = (getHeight() - this.cursorHalfWidth) / this.maxValue;
        while (i <= this.maxValue) {
            if (i == 8) {
                this.yLenght = AppUtils.dip2px(this.context, this.largeHeight);
            } else {
                this.yLenght = AppUtils.dip2px(this.context, this.smallHeight);
            }
            i++;
        }
        canvas.drawBitmap(this.bitmap, this.startX - (AppUtils.dip2px(this.context, this.largeHeight) / 3), (this.currentValue * this.gap) - this.cursorHalfWidth, this.yellowPaint);
    }

    public int getCurrentValue() {
        return this.currentValue;
    }

    public void setCurrentValue(int i) {
        this.currentValue = i;
        invalidate();
    }

    public int getMaxValue() {
        return this.maxValue;
    }
}
