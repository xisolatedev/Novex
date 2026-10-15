package com.cooingdv.rcufo.tools;

import android.app.Activity;
import java.util.Stack;

/* JADX INFO: loaded from: classes2.dex */
public class ActivityStack {
    private static Stack<Activity> mActivityStack = new Stack<>();
    private static ActivityStack instance = null;

    public static ActivityStack getInstance() {
        if (instance == null) {
            instance = new ActivityStack();
        }
        return instance;
    }

    public void popActivity(Activity activity) {
        if (activity != null) {
            activity.finish();
            mActivityStack.remove(activity);
        }
    }

    public void pushActivity(Activity activity) {
        if (activity != null) {
            mActivityStack.add(activity);
        }
    }

    public void clearAllActivity() {
        while (!mActivityStack.isEmpty()) {
            Activity activityPop = mActivityStack.pop();
            if (activityPop != null) {
                activityPop.finish();
            }
        }
    }
}
