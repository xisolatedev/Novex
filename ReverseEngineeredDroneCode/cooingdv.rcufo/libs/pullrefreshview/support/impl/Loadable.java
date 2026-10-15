package com.cooingdv.rcufo.libs.pullrefreshview.support.impl;

import com.cooingdv.rcufo.libs.pullrefreshview.layout.PullRefreshLayout;

/* JADX INFO: loaded from: classes2.dex */
public interface Loadable {
    boolean onScroll(float f);

    void onScrollChange(int i);

    boolean onStartFling(float f);

    void setPullRefreshLayout(PullRefreshLayout pullRefreshLayout);

    void startLoad();

    void stopLoad();
}
