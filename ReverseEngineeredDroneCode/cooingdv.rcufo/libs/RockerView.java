package com.cooingdv.rcufo.libs;

import android.content.Context;
import android.content.res.TypedArray;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Point;
import android.graphics.Rect;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import com.cooingdv.rcufo.C3033R;
import java.util.Timer;
import java.util.TimerTask;

/* JADX INFO: loaded from: classes2.dex */
public class RockerView extends View {
    private static final double ANGLE_0 = 0.0d;
    private static final double ANGLE_360 = 360.0d;
    private static final double ANGLE_4D_OF_0P = 0.0d;
    private static final double ANGLE_4D_OF_1P = 90.0d;
    private static final double ANGLE_4D_OF_2P = 180.0d;
    private static final double ANGLE_4D_OF_3P = 270.0d;
    private static final double ANGLE_8D_OF_0P = 22.5d;
    private static final double ANGLE_8D_OF_1P = 67.5d;
    private static final double ANGLE_8D_OF_2P = 112.5d;
    private static final double ANGLE_8D_OF_3P = 157.5d;
    private static final double ANGLE_8D_OF_4P = 202.5d;
    private static final double ANGLE_8D_OF_5P = 247.5d;
    private static final double ANGLE_8D_OF_6P = 292.5d;
    private static final double ANGLE_8D_OF_7P = 337.5d;
    private static final double ANGLE_HORIZONTAL_2D_OF_0P = 90.0d;
    private static final double ANGLE_HORIZONTAL_2D_OF_1P = 270.0d;
    private static final double ANGLE_ROTATE45_4D_OF_0P = 45.0d;
    private static final double ANGLE_ROTATE45_4D_OF_1P = 135.0d;
    private static final double ANGLE_ROTATE45_4D_OF_2P = 225.0d;
    private static final double ANGLE_ROTATE45_4D_OF_3P = 315.0d;
    private static final double ANGLE_VERTICAL_2D_OF_0P = 0.0d;
    private static final double ANGLE_VERTICAL_2D_OF_1P = 180.0d;
    private static final int AREA_BACKGROUND_MODE_COLOR = 1;
    private static final int AREA_BACKGROUND_MODE_DEFAULT = 3;
    private static final int AREA_BACKGROUND_MODE_PIC = 0;
    private static final int AREA_BACKGROUND_MODE_XML = 2;
    private static final float DEFAULT_ROCKER_SCALE = 0.5f;
    private static final int DEFAULT_SIZE = 500;
    private static final int MAX_OFFSET = 255;
    private static final int ROCKER_BACKGROUND_MODE_COLOR = 5;
    private static final int ROCKER_BACKGROUND_MODE_DEFAULT = 7;
    private static final int ROCKER_BACKGROUND_MODE_PIC = 4;
    private static final int ROCKER_BACKGROUND_MODE_XML = 6;
    private static final String TAG = "RockerView";
    private float baseDistance;

    /* JADX INFO: renamed from: cx */
    public int f10181cx;

    /* JADX INFO: renamed from: cy */
    public int f10182cy;
    private int distance;
    Rect dst;
    private boolean isFixHeight;
    private boolean isJohnCustomMode;
    private boolean isJohnGravityMode;
    public int isTounching;
    private float lastDistance;
    private int mAreaBackgroundMode;
    private Paint mAreaBackgroundPaint;
    private Bitmap mAreaBitmap;
    private int mAreaColor;
    private int mAreaRadius;
    private CallBackMode mCallBackMode;
    private Point mCenterPoint;
    private DirectionMode mDirectionMode;
    private int mDistanceLevel;
    private OnAngleChangeListener mOnAngleChangeListener;
    private OnDistanceLevelListener mOnDistanceLevelListener;
    private OnShakeListener mOnShakeListener;
    private float mPeerOffset;
    private int mRockerBackgroundMode;
    private Bitmap mRockerBitmap;
    private int mRockerColor;
    private Paint mRockerPaint;
    private Point mRockerPosition;
    private int mRockerRadius;
    private float mRockerScale;
    private Timer mTimer;
    private int sendFlag;
    Rect src;
    private Direction tempDirection;

    public enum CallBackMode {
        CALL_BACK_MODE_MOVE,
        CALL_BACK_MODE_STATE_CHANGE,
        CALL_BACK_MODE_STATE_DISTANCE_CHANGE
    }

    public enum Direction {
        DIRECTION_LEFT,
        DIRECTION_RIGHT,
        DIRECTION_UP,
        DIRECTION_DOWN,
        DIRECTION_UP_LEFT,
        DIRECTION_UP_RIGHT,
        DIRECTION_DOWN_LEFT,
        DIRECTION_DOWN_RIGHT,
        DIRECTION_CENTER
    }

    public enum DirectionMode {
        DIRECTION_2_HORIZONTAL,
        DIRECTION_2_VERTICAL,
        DIRECTION_4_ROTATE_0,
        DIRECTION_4_ROTATE_45,
        DIRECTION_8
    }

    public interface OnAngleChangeListener {
        void angle(RockerView rockerView, double d);

        void onFinish();

        void onStart();
    }

    public interface OnDistanceLevelListener {
        void onDistanceLevel(int i);
    }

    public interface OnShakeListener {
        void direction(RockerView rockerView, Direction direction, double d, int i, int i2);

        void onFinish(RockerView rockerView);

        void onMove(RockerView rockerView, float f, float f2, int i);

        void onShakeStart(RockerView rockerView);
    }

    public Point getmRockerPosition() {
        return this.mRockerPosition;
    }

    public void setmRockerPosition(Point point) {
        this.mRockerPosition = point;
    }

    public int getmAreaRadius() {
        return this.mAreaRadius;
    }

    public RockerView(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
        this.mCallBackMode = CallBackMode.CALL_BACK_MODE_MOVE;
        this.tempDirection = Direction.DIRECTION_CENTER;
        this.lastDistance = 0.0f;
        this.isFixHeight = false;
        this.baseDistance = 0.0f;
        this.mDistanceLevel = 10;
        this.mAreaBackgroundMode = 3;
        this.mRockerBackgroundMode = 7;
        this.isJohnCustomMode = false;
        this.isJohnGravityMode = false;
        this.sendFlag = 0;
        this.isTounching = 0;
        this.mTimer = new Timer();
        this.src = new Rect();
        this.dst = new Rect();
        initAttribute(context, attributeSet);
        isInEditMode();
        Paint paint = new Paint();
        this.mAreaBackgroundPaint = paint;
        paint.setAntiAlias(true);
        Paint paint2 = new Paint();
        this.mRockerPaint = paint2;
        paint2.setAntiAlias(true);
        this.mCenterPoint = new Point();
        this.mRockerPosition = new Point();
    }

    @Override // android.view.View
    protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
    }

    private void initAttribute(Context context, AttributeSet attributeSet) {
        TypedArray typedArrayObtainStyledAttributes = context.obtainStyledAttributes(attributeSet, C3033R.styleable.RockerView);
        Drawable drawable = typedArrayObtainStyledAttributes.getDrawable(0);
        if (drawable != null) {
            if (drawable instanceof BitmapDrawable) {
                this.mAreaBitmap = ((BitmapDrawable) drawable).getBitmap();
                this.mAreaBackgroundMode = 0;
            } else if (drawable instanceof GradientDrawable) {
                this.mAreaBitmap = drawable2Bitmap(drawable);
                this.mAreaBackgroundMode = 2;
            } else if (drawable instanceof ColorDrawable) {
                this.mAreaColor = ((ColorDrawable) drawable).getColor();
                this.mAreaBackgroundMode = 1;
            } else {
                this.mAreaBackgroundMode = 3;
            }
        } else {
            this.mAreaBackgroundMode = 3;
        }
        Drawable drawable2 = typedArrayObtainStyledAttributes.getDrawable(1);
        if (drawable2 != null) {
            if (drawable2 instanceof BitmapDrawable) {
                this.mRockerBitmap = ((BitmapDrawable) drawable2).getBitmap();
                this.mRockerBackgroundMode = 4;
            } else if (drawable2 instanceof GradientDrawable) {
                this.mRockerBitmap = drawable2Bitmap(drawable2);
                this.mRockerBackgroundMode = 6;
            } else if (drawable2 instanceof ColorDrawable) {
                this.mRockerColor = ((ColorDrawable) drawable2).getColor();
                this.mRockerBackgroundMode = 5;
            } else {
                this.mRockerBackgroundMode = 7;
            }
        } else {
            this.mRockerBackgroundMode = 7;
        }
        this.mRockerScale = typedArrayObtainStyledAttributes.getFloat(3, DEFAULT_ROCKER_SCALE);
        this.mDistanceLevel = typedArrayObtainStyledAttributes.getInt(4, 10);
        this.mCallBackMode = getCallBackMode(typedArrayObtainStyledAttributes.getInt(2, 0));
        this.mPeerOffset = 25.5f;
        typedArrayObtainStyledAttributes.recycle();
    }

    @Override // android.view.View
    protected void onMeasure(int i, int i2) {
        int mode = View.MeasureSpec.getMode(i);
        int mode2 = View.MeasureSpec.getMode(i2);
        int size = View.MeasureSpec.getSize(i);
        int size2 = View.MeasureSpec.getSize(i2);
        if (mode != 1073741824) {
            size = 500;
        }
        if (mode2 != 1073741824) {
            size2 = 500;
        }
        setMeasuredDimension(size, size2);
    }

    @Override // android.view.View
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int measuredWidth = getMeasuredWidth();
        int measuredHeight = getMeasuredHeight();
        int i = measuredWidth / 2;
        this.f10181cx = i;
        int i2 = measuredHeight / 2;
        this.f10182cy = i2;
        this.mCenterPoint.set(i, i2);
        int i3 = (int) ((measuredWidth <= measuredHeight ? this.f10181cx : this.f10182cy) / (this.mRockerScale + 1.0f));
        this.mAreaRadius = i3;
        this.mRockerRadius = (int) (i3 * this.mRockerScale);
        if (this.mRockerPosition.x == 0 || this.mRockerPosition.y == 0) {
            if (this.isFixHeight) {
                this.mRockerPosition.set(this.mCenterPoint.x, this.mCenterPoint.y);
            } else {
                this.mRockerPosition.set(this.mCenterPoint.x, measuredHeight - this.mRockerRadius);
            }
        }
        int i4 = this.mAreaBackgroundMode;
        if (i4 == 0 || 2 == i4) {
            this.src.set(0, 0, this.mAreaBitmap.getWidth(), this.mAreaBitmap.getHeight());
            this.dst.set(this.mCenterPoint.x - this.mAreaRadius, this.mCenterPoint.y - this.mAreaRadius, this.mCenterPoint.x + this.mAreaRadius, this.mCenterPoint.y + this.mAreaRadius);
            canvas.drawBitmap(this.mAreaBitmap, this.src, this.dst, this.mAreaBackgroundPaint);
        } else if (1 == i4) {
            this.mAreaBackgroundPaint.setColor(this.mAreaColor);
            canvas.drawCircle(this.mCenterPoint.x, this.mCenterPoint.y, this.mAreaRadius, this.mAreaBackgroundPaint);
        } else {
            this.mAreaBackgroundPaint.setColor(-7829368);
            canvas.drawCircle(this.mCenterPoint.x, this.mCenterPoint.y, this.mAreaRadius, this.mAreaBackgroundPaint);
        }
        int i5 = this.mRockerBackgroundMode;
        if (4 == i5 || 6 == i5) {
            this.src.set(0, 0, this.mRockerBitmap.getWidth(), this.mRockerBitmap.getHeight());
            this.dst.set(this.mRockerPosition.x - this.mRockerRadius, this.mRockerPosition.y - this.mRockerRadius, this.mRockerPosition.x + this.mRockerRadius, this.mRockerPosition.y + this.mRockerRadius);
            canvas.drawBitmap(this.mRockerBitmap, this.src, this.dst, this.mRockerPaint);
        } else if (5 == i5) {
            this.mRockerPaint.setColor(this.mRockerColor);
            canvas.drawCircle(this.mRockerPosition.x, this.mRockerPosition.y, this.mRockerRadius, this.mRockerPaint);
        } else {
            this.mRockerPaint.setColor(-65536);
            canvas.drawCircle(this.mRockerPosition.x, this.mRockerPosition.y, this.mRockerRadius, this.mRockerPaint);
        }
    }

    @Override // android.view.View
    public boolean onTouchEvent(MotionEvent motionEvent) {
        if (this.isJohnGravityMode) {
            return true;
        }
        int action = motionEvent.getAction();
        if (action == 0) {
            this.isTounching = 1;
            callBackStart();
        } else {
            if (action != 1) {
                if (action != 2) {
                    if (action == 3) {
                    }
                }
                return true;
            }
            this.isTounching = 0;
            this.isTounching = 0;
            callBackFinish(this);
            float x = motionEvent.getX();
            float y = motionEvent.getY();
            this.distance = 0;
            if (this.isFixHeight) {
                OnShakeListener onShakeListener = this.mOnShakeListener;
                if (onShakeListener != null) {
                    onShakeListener.direction(this, Direction.DIRECTION_CENTER, 0.0d, 0, 0);
                    this.mOnShakeListener.onMove(this, 0.0f, 0.0f, this.mAreaRadius + this.mRockerRadius);
                }
                moveRocker(this.mCenterPoint.x, this.mCenterPoint.y);
            } else {
                Point point = this.mCenterPoint;
                Point point2 = new Point((int) x, (int) y);
                int i = this.mAreaRadius;
                int i2 = this.mRockerRadius;
                Point rockerPositionPoint = getRockerPositionPoint(point, point2, i + i2, i2);
                if (this.mOnShakeListener != null) {
                    int i3 = (int) (this.mCenterPoint.y - y);
                    int i4 = this.mAreaRadius;
                    int i5 = this.mRockerRadius;
                    if (i3 < (-(i4 + i5))) {
                        i3 = -(i4 + i5);
                    }
                    if (i3 > i4 + i5) {
                        i3 = i4 + i5;
                    }
                    this.mOnShakeListener.onMove(this, 0.0f, i3, i4 + i5);
                }
                moveRocker(this.mCenterPoint.x, rockerPositionPoint.y);
            }
            return true;
        }
        this.isTounching = 1;
        float x2 = motionEvent.getX();
        float y2 = motionEvent.getY();
        this.baseDistance = this.mAreaRadius + 2;
        Point point3 = this.mCenterPoint;
        Point point4 = new Point((int) x2, (int) y2);
        int i6 = this.mAreaRadius;
        int i7 = this.mRockerRadius;
        Point rockerPositionPoint2 = getRockerPositionPoint(point3, point4, i6 + i7, i7);
        this.mRockerPosition = rockerPositionPoint2;
        moveRocker(rockerPositionPoint2.x, this.mRockerPosition.y);
        return true;
    }

    public void setPosition(int i, int i2) {
        int i3 = (this.mAreaRadius + this.mRockerRadius) * 2;
        Point point = this.mCenterPoint;
        Point point2 = new Point((i * i3) / 100, (i3 * i2) / 100);
        int i4 = this.mAreaRadius;
        int i5 = this.mRockerRadius;
        Point rockerPositionPoint = getRockerPositionPoint(point, point2, i4 + i5, i5);
        this.mRockerPosition = rockerPositionPoint;
        moveRocker(rockerPositionPoint.x, this.mRockerPosition.y);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public Point getRockerPositionPoint(Point point, Point point2, float f, float f2) {
        float f3 = point2.x - point.x;
        float f4 = point2.y - point.y;
        float fSqrt = (float) Math.sqrt((f3 * f3) + (f4 * f4));
        double dAcos = Math.acos(f3 / fSqrt) * ((double) (point2.y < point.y ? -1 : 1));
        double dRadian2Angle = radian2Angle(dAcos);
        int i = point2.x - point.x;
        int i2 = point.y - point2.y;
        float f5 = -f;
        if (i < f5) {
            i = (int) f5;
        }
        if (i > f) {
            i = (int) f;
        }
        int i3 = i;
        if (i2 < f5) {
            i2 = (int) f5;
        }
        int i4 = ((float) i2) > f ? (int) f : i2;
        float f6 = fSqrt + f2;
        if (f6 <= f) {
            if (!this.isFixHeight || f6 >= (f * 2.0f) / 5.0f) {
                callBack(dRadian2Angle, (int) fSqrt, point2.y, i3, i4);
            }
            return point2;
        }
        double d = f - f2;
        int iCos = (int) (((double) point.x) + (Math.cos(dAcos) * d));
        int iSin = (int) (((double) point.y) + (d * Math.sin(dAcos)));
        callBack(dRadian2Angle, (int) Math.sqrt(((iCos - point.x) * (iCos - point.x)) + ((iSin - point.y) * (iSin - point.y))), iSin, i3, i4);
        return new Point(iCos, iSin);
    }

    public void moveRocker(float f, float f2) {
        this.sendFlag = 0;
        this.mRockerPosition.set((int) f, (int) f2);
        invalidate();
    }

    private double radian2Angle(double d) {
        double dRound = Math.round((d / 3.141592653589793d) * 180.0d);
        return dRound >= 0.0d ? dRound : dRound + ANGLE_360;
    }

    private Bitmap drawable2Bitmap(Drawable drawable) {
        int intrinsicWidth = drawable.getIntrinsicWidth();
        int intrinsicHeight = drawable.getIntrinsicHeight();
        Bitmap bitmapCreateBitmap = Bitmap.createBitmap(intrinsicWidth, intrinsicHeight, drawable.getOpacity() != -1 ? Bitmap.Config.ARGB_8888 : Bitmap.Config.RGB_565);
        Canvas canvas = new Canvas(bitmapCreateBitmap);
        drawable.setBounds(0, 0, intrinsicWidth, intrinsicHeight);
        drawable.draw(canvas);
        return bitmapCreateBitmap;
    }

    private void callBackStart() {
        this.tempDirection = Direction.DIRECTION_CENTER;
        OnAngleChangeListener onAngleChangeListener = this.mOnAngleChangeListener;
        if (onAngleChangeListener != null) {
            onAngleChangeListener.onStart();
        }
        OnShakeListener onShakeListener = this.mOnShakeListener;
        if (onShakeListener != null) {
            onShakeListener.onShakeStart(this);
        }
    }

    private void callBack(double d, int i, int i2, int i3, int i4) {
        float f = i;
        float fAbs = Math.abs(f - this.lastDistance);
        float f2 = this.baseDistance;
        int i5 = this.mDistanceLevel;
        if (fAbs >= f2 / i5) {
            this.lastDistance = f;
            OnDistanceLevelListener onDistanceLevelListener = this.mOnDistanceLevelListener;
            if (onDistanceLevelListener != null) {
                onDistanceLevelListener.onDistanceLevel((int) (f / (f2 / i5)));
            }
        }
        OnAngleChangeListener onAngleChangeListener = this.mOnAngleChangeListener;
        if (onAngleChangeListener != null) {
            onAngleChangeListener.angle(this, d);
        }
        int offset = getOffset(i2);
        OnShakeListener onShakeListener = this.mOnShakeListener;
        if (onShakeListener != null) {
            onShakeListener.onMove(this, i3, i4, this.mAreaRadius + this.mRockerRadius);
            if (CallBackMode.CALL_BACK_MODE_MOVE == this.mCallBackMode) {
                int i6 = C30822.$SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode[this.mDirectionMode.ordinal()];
                if (i6 != 1) {
                    if (i6 != 2) {
                        if (i6 != 3) {
                            if (i6 != 4) {
                                if (i6 == 5) {
                                    if ((0.0d <= d && ANGLE_8D_OF_0P > d) || (ANGLE_8D_OF_7P <= d && ANGLE_360 > d)) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                                    } else if (ANGLE_8D_OF_0P <= d && ANGLE_8D_OF_1P > d) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_RIGHT, d, 0, i);
                                    } else if (ANGLE_8D_OF_1P <= d && ANGLE_8D_OF_2P > d) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, 0, i);
                                    } else if (ANGLE_8D_OF_2P <= d && ANGLE_8D_OF_3P > d) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_3P <= d && ANGLE_8D_OF_4P > d) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_4P <= d && ANGLE_8D_OF_5P > d) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_5P <= d && ANGLE_8D_OF_6P > d) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, 0, i);
                                    } else if (ANGLE_8D_OF_6P <= d && ANGLE_8D_OF_7P > d) {
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_RIGHT, d, 0, i);
                                    }
                                }
                            } else if ((0.0d <= d && ANGLE_ROTATE45_4D_OF_0P > d) || (ANGLE_ROTATE45_4D_OF_3P <= d && ANGLE_360 > d)) {
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_0P <= d && ANGLE_ROTATE45_4D_OF_1P > d) {
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_1P <= d && ANGLE_ROTATE45_4D_OF_2P > d) {
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_2P <= d && ANGLE_ROTATE45_4D_OF_3P > d) {
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, 0, i);
                            }
                        } else if (0.0d <= d && 90.0d > d) {
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_RIGHT, d, 0, i);
                        } else if (90.0d <= d && 180.0d > d) {
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_LEFT, d, 0, i);
                        } else if (180.0d <= d && 270.0d > d) {
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_LEFT, d, 0, i);
                        } else if (270.0d <= d && ANGLE_360 > d) {
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_RIGHT, d, 0, i);
                        }
                    } else if (0.0d <= d && 180.0d > d) {
                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, offset, i);
                    } else if (180.0d <= d && ANGLE_360 > d) {
                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, offset, i);
                    }
                } else if ((0.0d <= d && 90.0d > d) || (270.0d <= d && ANGLE_360 > d)) {
                    this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                } else if (90.0d <= d && 270.0d > d) {
                    this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                }
            } else if (CallBackMode.CALL_BACK_MODE_STATE_CHANGE == this.mCallBackMode) {
                int i7 = C30822.$SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode[this.mDirectionMode.ordinal()];
                if (i7 != 1) {
                    if (i7 != 2) {
                        if (i7 != 3) {
                            if (i7 != 4) {
                                if (i7 == 5) {
                                    if (((0.0d <= d && ANGLE_8D_OF_0P > d) || (ANGLE_8D_OF_7P <= d && ANGLE_360 > d)) && this.tempDirection != Direction.DIRECTION_RIGHT) {
                                        this.tempDirection = Direction.DIRECTION_RIGHT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                                    } else if (ANGLE_8D_OF_0P <= d && ANGLE_8D_OF_1P > d && this.tempDirection != Direction.DIRECTION_DOWN_RIGHT) {
                                        this.tempDirection = Direction.DIRECTION_DOWN_RIGHT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_RIGHT, d, 0, i);
                                    } else if (ANGLE_8D_OF_1P <= d && ANGLE_8D_OF_2P > d && this.tempDirection != Direction.DIRECTION_DOWN) {
                                        this.tempDirection = Direction.DIRECTION_DOWN;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, 0, i);
                                    } else if (ANGLE_8D_OF_2P <= d && ANGLE_8D_OF_3P > d && this.tempDirection != Direction.DIRECTION_DOWN_LEFT) {
                                        this.tempDirection = Direction.DIRECTION_DOWN_LEFT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_3P <= d && ANGLE_8D_OF_4P > d && this.tempDirection != Direction.DIRECTION_LEFT) {
                                        this.tempDirection = Direction.DIRECTION_LEFT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_4P <= d && ANGLE_8D_OF_5P > d && this.tempDirection != Direction.DIRECTION_UP_LEFT) {
                                        this.tempDirection = Direction.DIRECTION_UP_LEFT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_5P <= d && ANGLE_8D_OF_6P > d && this.tempDirection != Direction.DIRECTION_UP) {
                                        this.tempDirection = Direction.DIRECTION_UP;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, 0, i);
                                    } else if (ANGLE_8D_OF_6P <= d && ANGLE_8D_OF_7P > d && this.tempDirection != Direction.DIRECTION_UP_RIGHT) {
                                        this.tempDirection = Direction.DIRECTION_UP_RIGHT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_RIGHT, d, 0, i);
                                    }
                                }
                            } else if (((0.0d <= d && ANGLE_ROTATE45_4D_OF_0P > d) || (ANGLE_ROTATE45_4D_OF_3P <= d && ANGLE_360 > d)) && this.tempDirection != Direction.DIRECTION_RIGHT) {
                                this.tempDirection = Direction.DIRECTION_RIGHT;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_0P <= d && ANGLE_ROTATE45_4D_OF_1P > d && this.tempDirection != Direction.DIRECTION_DOWN) {
                                this.tempDirection = Direction.DIRECTION_DOWN;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_1P <= d && ANGLE_ROTATE45_4D_OF_2P > d && this.tempDirection != Direction.DIRECTION_LEFT) {
                                this.tempDirection = Direction.DIRECTION_LEFT;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_2P <= d && ANGLE_ROTATE45_4D_OF_3P > d && this.tempDirection != Direction.DIRECTION_UP) {
                                this.tempDirection = Direction.DIRECTION_UP;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, 0, i);
                            }
                        } else if (0.0d <= d && 90.0d > d && this.tempDirection != Direction.DIRECTION_DOWN_RIGHT) {
                            this.tempDirection = Direction.DIRECTION_DOWN_RIGHT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_RIGHT, d, 0, i);
                        } else if (90.0d <= d && 180.0d > d && this.tempDirection != Direction.DIRECTION_DOWN_LEFT) {
                            this.tempDirection = Direction.DIRECTION_DOWN_LEFT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_LEFT, d, 0, i);
                        } else if (180.0d <= d && 270.0d > d && this.tempDirection != Direction.DIRECTION_UP_LEFT) {
                            this.tempDirection = Direction.DIRECTION_UP_LEFT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_LEFT, d, 0, i);
                        } else if (270.0d <= d && ANGLE_360 > d && this.tempDirection != Direction.DIRECTION_UP_RIGHT) {
                            this.tempDirection = Direction.DIRECTION_UP_RIGHT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_RIGHT, d, 0, i);
                        }
                    } else if (0.0d <= d && 180.0d > d && this.tempDirection != Direction.DIRECTION_DOWN) {
                        this.tempDirection = Direction.DIRECTION_DOWN;
                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, offset, i);
                    } else if (180.0d <= d && ANGLE_360 > d && this.tempDirection != Direction.DIRECTION_UP) {
                        this.tempDirection = Direction.DIRECTION_UP;
                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, offset, i);
                    }
                } else if (((0.0d <= d && 90.0d > d) || (270.0d <= d && ANGLE_360 > d)) && this.tempDirection != Direction.DIRECTION_RIGHT) {
                    this.tempDirection = Direction.DIRECTION_RIGHT;
                    this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                } else if (90.0d <= d && 270.0d > d && this.tempDirection != Direction.DIRECTION_LEFT) {
                    this.tempDirection = Direction.DIRECTION_LEFT;
                    this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                }
            } else if (CallBackMode.CALL_BACK_MODE_STATE_DISTANCE_CHANGE == this.mCallBackMode) {
                int i8 = C30822.$SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode[this.mDirectionMode.ordinal()];
                if (i8 != 1) {
                    if (i8 != 2) {
                        if (i8 != 3) {
                            if (i8 != 4) {
                                if (i8 == 5) {
                                    if (((0.0d <= d && ANGLE_8D_OF_0P > d) || (ANGLE_8D_OF_7P <= d && ANGLE_360 > d)) && (this.tempDirection != Direction.DIRECTION_RIGHT || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_RIGHT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                                    } else if (ANGLE_8D_OF_0P <= d && ANGLE_8D_OF_1P > d && (this.tempDirection != Direction.DIRECTION_DOWN_RIGHT || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_DOWN_RIGHT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_RIGHT, d, 0, i);
                                    } else if (ANGLE_8D_OF_1P <= d && ANGLE_8D_OF_2P > d && (this.tempDirection != Direction.DIRECTION_DOWN || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_DOWN;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, 0, i);
                                    } else if (ANGLE_8D_OF_2P <= d && ANGLE_8D_OF_3P > d && (this.tempDirection != Direction.DIRECTION_DOWN_LEFT || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_DOWN_LEFT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_3P <= d && ANGLE_8D_OF_4P > d && (this.tempDirection != Direction.DIRECTION_LEFT || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_LEFT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_4P <= d && ANGLE_8D_OF_5P > d && (this.tempDirection != Direction.DIRECTION_UP_LEFT || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_UP_LEFT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_LEFT, d, 0, i);
                                    } else if (ANGLE_8D_OF_5P <= d && ANGLE_8D_OF_6P > d && (this.tempDirection != Direction.DIRECTION_UP || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_UP;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, 0, i);
                                    } else if (ANGLE_8D_OF_6P <= d && ANGLE_8D_OF_7P > d && (this.tempDirection != Direction.DIRECTION_UP_RIGHT || i != this.distance)) {
                                        this.tempDirection = Direction.DIRECTION_UP_RIGHT;
                                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_RIGHT, d, 0, i);
                                    }
                                }
                            } else if (((0.0d <= d && ANGLE_ROTATE45_4D_OF_0P > d) || (ANGLE_ROTATE45_4D_OF_3P <= d && ANGLE_360 > d)) && (this.tempDirection != Direction.DIRECTION_RIGHT || i != this.distance)) {
                                this.tempDirection = Direction.DIRECTION_RIGHT;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_0P <= d && ANGLE_ROTATE45_4D_OF_1P > d && (this.tempDirection != Direction.DIRECTION_DOWN || i != this.distance)) {
                                this.tempDirection = Direction.DIRECTION_DOWN;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_1P <= d && ANGLE_ROTATE45_4D_OF_2P > d && (this.tempDirection != Direction.DIRECTION_LEFT || i != this.distance)) {
                                this.tempDirection = Direction.DIRECTION_LEFT;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                            } else if (ANGLE_ROTATE45_4D_OF_2P <= d && ANGLE_ROTATE45_4D_OF_3P > d && (this.tempDirection != Direction.DIRECTION_UP || i != this.distance)) {
                                this.tempDirection = Direction.DIRECTION_UP;
                                this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, 0, i);
                            }
                        } else if (0.0d <= d && 90.0d > d && (this.tempDirection != Direction.DIRECTION_DOWN_RIGHT || i != this.distance)) {
                            this.tempDirection = Direction.DIRECTION_DOWN_RIGHT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_RIGHT, d, 0, i);
                        } else if (90.0d <= d && 180.0d > d && (this.tempDirection != Direction.DIRECTION_DOWN_LEFT || i != this.distance)) {
                            this.tempDirection = Direction.DIRECTION_DOWN_LEFT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN_LEFT, d, 0, i);
                        } else if (180.0d <= d && 270.0d > d && (this.tempDirection != Direction.DIRECTION_UP_LEFT || i != this.distance)) {
                            this.tempDirection = Direction.DIRECTION_UP_LEFT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_LEFT, d, 0, i);
                        } else if (270.0d <= d && ANGLE_360 > d && (this.tempDirection != Direction.DIRECTION_UP_RIGHT || i != this.distance)) {
                            this.tempDirection = Direction.DIRECTION_UP_RIGHT;
                            this.mOnShakeListener.direction(this, Direction.DIRECTION_UP_RIGHT, d, 0, i);
                        }
                    } else if (0.0d <= d && 180.0d > d && (this.tempDirection != Direction.DIRECTION_DOWN || i != this.distance)) {
                        this.tempDirection = Direction.DIRECTION_DOWN;
                        this.mOnShakeListener.direction(this, Direction.DIRECTION_DOWN, d, offset, i);
                    } else if (180.0d <= d && ANGLE_360 > d && (this.tempDirection != Direction.DIRECTION_UP || i != this.distance)) {
                        this.tempDirection = Direction.DIRECTION_UP;
                        this.mOnShakeListener.direction(this, Direction.DIRECTION_UP, d, offset, i);
                    }
                } else if (((0.0d <= d && 90.0d > d) || (270.0d <= d && ANGLE_360 > d)) && (this.tempDirection != Direction.DIRECTION_RIGHT || i != this.distance)) {
                    this.tempDirection = Direction.DIRECTION_RIGHT;
                    this.mOnShakeListener.direction(this, Direction.DIRECTION_RIGHT, d, 0, i);
                } else if (90.0d <= d && 270.0d > d && (this.tempDirection != Direction.DIRECTION_LEFT || i != this.distance)) {
                    this.tempDirection = Direction.DIRECTION_LEFT;
                    this.mOnShakeListener.direction(this, Direction.DIRECTION_LEFT, d, 0, i);
                }
            }
            this.distance = i;
        }
    }

    /* JADX INFO: renamed from: com.cooingdv.rcufo.libs.RockerView$2 */
    static /* synthetic */ class C30822 {
        static final /* synthetic */ int[] $SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode;

        static {
            int[] iArr = new int[DirectionMode.values().length];
            $SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode = iArr;
            try {
                iArr[DirectionMode.DIRECTION_2_HORIZONTAL.ordinal()] = 1;
            } catch (NoSuchFieldError unused) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode[DirectionMode.DIRECTION_2_VERTICAL.ordinal()] = 2;
            } catch (NoSuchFieldError unused2) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode[DirectionMode.DIRECTION_4_ROTATE_0.ordinal()] = 3;
            } catch (NoSuchFieldError unused3) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode[DirectionMode.DIRECTION_4_ROTATE_45.ordinal()] = 4;
            } catch (NoSuchFieldError unused4) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$libs$RockerView$DirectionMode[DirectionMode.DIRECTION_8.ordinal()] = 5;
            } catch (NoSuchFieldError unused5) {
            }
        }
    }

    public void setFixHeight(boolean z) {
        this.isFixHeight = z;
        if (z) {
            moveRocker(this.mCenterPoint.x, this.mCenterPoint.y);
        } else {
            moveRocker(this.mCenterPoint.x, Math.abs(getMeasuredHeight() - this.mRockerRadius));
        }
    }

    public void setIsJohnCustomMode(boolean z) {
        this.isJohnCustomMode = z;
    }

    public void setIsGravityMode(boolean z) {
        this.isJohnGravityMode = z;
    }

    public boolean getIsJohnCustomMode() {
        return this.isJohnCustomMode;
    }

    private void callBackFinish(RockerView rockerView) {
        this.tempDirection = Direction.DIRECTION_CENTER;
        OnAngleChangeListener onAngleChangeListener = this.mOnAngleChangeListener;
        if (onAngleChangeListener != null) {
            onAngleChangeListener.onFinish();
        }
        OnShakeListener onShakeListener = this.mOnShakeListener;
        if (onShakeListener != null) {
            onShakeListener.onFinish(rockerView);
        }
    }

    public int getRegionRadius() {
        return this.mAreaRadius;
    }

    public void setCallBackMode(CallBackMode callBackMode) {
        this.mCallBackMode = callBackMode;
    }

    private int getOffset(int i) {
        int i2 = this.mRockerRadius + 5;
        int measuredHeight = (getMeasuredHeight() - this.mRockerRadius) - 5;
        int i3 = measuredHeight - i2;
        if (i <= i2) {
            return 255;
        }
        if (i >= measuredHeight) {
            return 0;
        }
        return (int) ((((measuredHeight - i) * 10) / i3) * this.mPeerOffset);
    }

    public void setOnAngleChangeListener(OnAngleChangeListener onAngleChangeListener) {
        this.mOnAngleChangeListener = onAngleChangeListener;
    }

    public void setOnShakeListener(DirectionMode directionMode, OnShakeListener onShakeListener) {
        this.mDirectionMode = directionMode;
        this.mOnShakeListener = onShakeListener;
    }

    public void setOnDistanceLevelListener(OnDistanceLevelListener onDistanceLevelListener) {
        this.mOnDistanceLevelListener = onDistanceLevelListener;
    }

    private CallBackMode getCallBackMode(int i) {
        if (i == 0) {
            return CallBackMode.CALL_BACK_MODE_MOVE;
        }
        if (i == 1) {
            return CallBackMode.CALL_BACK_MODE_STATE_CHANGE;
        }
        return this.mCallBackMode;
    }

    public void controlRise() {
        voiceControl(new Point(this.f10181cx, this.f10182cy - this.mAreaRadius), 500L, this.isFixHeight);
    }

    public void controlDrop() {
        voiceControl(new Point(this.f10181cx, this.f10182cy + this.mAreaRadius), 1000L, this.isFixHeight);
    }

    public void controlTurnLeft() {
        voiceControl(new Point(this.f10181cx - this.mAreaRadius, this.f10182cy), 500L, true);
    }

    public void controlTurnRight() {
        voiceControl(new Point(this.f10181cx + this.mAreaRadius, this.f10182cy), 500L, true);
    }

    public void controlForward() {
        voiceControl(new Point(this.f10181cx, this.f10182cy - this.mAreaRadius), 1500L, this.isFixHeight);
    }

    public void controlBackward() {
        voiceControl(new Point(this.f10181cx, this.f10182cy + this.mAreaRadius), 1500L, this.isFixHeight);
    }

    public void controlLeft() {
        voiceControl(new Point(this.f10181cx - this.mAreaRadius, this.f10182cy), 1500L, this.isFixHeight);
    }

    public void controlRight() {
        voiceControl(new Point(this.f10181cx + this.mAreaRadius, this.f10182cy), 1500L, this.isFixHeight);
    }

    private void voiceControl(Point point, long j, boolean z) {
        Point point2 = this.mCenterPoint;
        int i = this.mAreaRadius;
        int i2 = this.mRockerRadius;
        Point rockerPositionPoint = getRockerPositionPoint(point2, point, i + i2, i2);
        this.mRockerPosition = rockerPositionPoint;
        moveRocker(rockerPositionPoint.x, this.mRockerPosition.y);
        if (z) {
            this.mTimer.schedule(new TimerTask() { // from class: com.cooingdv.rcufo.libs.RockerView.1
                @Override // java.util.TimerTask, java.lang.Runnable
                public void run() {
                    RockerView rockerView = RockerView.this;
                    rockerView.mRockerPosition = rockerView.getRockerPositionPoint(rockerView.mCenterPoint, new Point(RockerView.this.f10181cx, RockerView.this.f10182cy), RockerView.this.mAreaRadius + RockerView.this.mRockerRadius, RockerView.this.mRockerRadius);
                    RockerView rockerView2 = RockerView.this;
                    rockerView2.moveRocker(rockerView2.mRockerPosition.x, RockerView.this.mRockerPosition.y);
                    OnShakeListener onShakeListener = RockerView.this.mOnShakeListener;
                    RockerView rockerView3 = RockerView.this;
                    onShakeListener.onMove(rockerView3, 0.0f, 0.0f, rockerView3.mAreaRadius + RockerView.this.mRockerRadius);
                }
            }, j);
        }
    }
}
