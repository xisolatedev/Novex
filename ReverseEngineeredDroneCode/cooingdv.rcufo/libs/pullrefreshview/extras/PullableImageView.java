package com.cooingdv.rcufo.libs.pullrefreshview.extras;

import android.content.Context;
import android.util.AttributeSet;
import androidx.appcompat.widget.AppCompatImageView;
import com.cooingdv.rcufo.libs.pullrefreshview.support.impl.Pullable;

/* JADX INFO: loaded from: classes2.dex */
public class PullableImageView extends AppCompatImageView implements Pullable {
    @Override // com.cooingdv.rcufo.libs.pullrefreshview.support.impl.Pullable
    public boolean isGetBottom() {
        return true;
    }

    @Override // com.cooingdv.rcufo.libs.pullrefreshview.support.impl.Pullable
    public boolean isGetTop() {
        return true;
    }

    public PullableImageView(Context context) {
        super(context);
    }

    public PullableImageView(Context context, AttributeSet attributeSet) {
        super(context, attributeSet);
    }

    public PullableImageView(Context context, AttributeSet attributeSet, int i) {
        super(context, attributeSet, i);
    }
}
