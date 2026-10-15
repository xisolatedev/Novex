package com.cooingdv.rcufo.libs.pullrefreshview.extras;

import android.content.Context;
import android.text.method.ScrollingMovementMethod;
import android.util.AttributeSet;
import androidx.appcompat.widget.AppCompatTextView;
import com.cooingdv.rcufo.libs.pullrefreshview.support.impl.OnScrollListener;
import com.cooingdv.rcufo.libs.pullrefreshview.support.impl.Pullable;

/* JADX INFO: loaded from: classes2.dex */
public class PullableTextView extends AppCompatTextView implements Pullable {
    private OnScrollListener onScrollListener;

    public PullableTextView(Context context) {
        super(context);
        this.onScrollListener = null;
        setMovementMethod(ScrollingMovementMethod.getInstance());
    }

    public PullableTextView(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
        this.onScrollListener = null;
        setMovementMethod(ScrollingMovementMethod.getInstance());
    }

    public PullableTextView(Context context, AttributeSet attributeSet, int i) {
        super(context, attributeSet, i);
        this.onScrollListener = null;
        setMovementMethod(ScrollingMovementMethod.getInstance());
    }

    @Override // com.cooingdv.rcufo.libs.pullrefreshview.support.impl.Pullable
    public boolean isGetTop() {
        return getScrollY() == 0;
    }

    @Override // com.cooingdv.rcufo.libs.pullrefreshview.support.impl.Pullable
    public boolean isGetBottom() {
        return getScrollY() >= ((getLayout().getHeight() - getMeasuredHeight()) + getCompoundPaddingBottom()) + getCompoundPaddingTop();
    }

    public void setOnScrollListener(OnScrollListener onScrollListener) {
        this.onScrollListener = onScrollListener;
    }

    @Override // android.widget.TextView, android.view.View
    protected void onScrollChanged(int i, int i2, int i3, int i4) {
        super.onScrollChanged(i, i2, i3, i4);
        OnScrollListener onScrollListener = this.onScrollListener;
        if (onScrollListener != null) {
            onScrollListener.onScrollChanged(this, i, i2, i3, i4);
        }
    }
}
