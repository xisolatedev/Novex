package com.cooingdv.rcufo.adapter;

import android.content.Context;
import android.text.TextUtils;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.ImageView;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.utils.AppUtils;
import java.util.List;
import java.util.Map;

/* JADX INFO: loaded from: classes2.dex */
public class TopListViewAdapter extends BaseAdapter {
    private List<String> itemList;
    private Context mContext;
    private Map<String, Integer> resMap;
    private String TAG = getClass().getSimpleName();
    private boolean isRecordVideo = false;
    private boolean isControlMode = false;
    private boolean isGestureMode = false;
    private boolean isFixedHeightMode = false;
    private boolean isTurn180 = false;
    private boolean isMenuOpen = false;
    private int currPower = 4;
    private String timer = "";

    public static class ViewHolder {
        public ImageView imageView;
        public TextView textView;
    }

    @Override // android.widget.Adapter
    public long getItemId(int i) {
        return i;
    }

    public void setTimer(String str) {
        this.timer = str;
    }

    public int getCurrPower() {
        return this.currPower;
    }

    public void setCurrPower(int i) {
        this.currPower = i;
    }

    public boolean isControlMode() {
        return this.isControlMode;
    }

    public void setControlMode(boolean z) {
        Log.e(this.TAG, z + "=work Mode");
        this.isControlMode = z;
    }

    public void setResMap(Map<String, Integer> map) {
        this.resMap = map;
    }

    public void setRecordVideo(boolean z) {
        Log.e(this.TAG, "setRecordVideo;" + z);
        this.isRecordVideo = z;
    }

    public boolean isFixedHeightMode() {
        return this.isFixedHeightMode;
    }

    public void setFixedHeightMode(boolean z) {
        this.isFixedHeightMode = z;
    }

    public boolean isGestureMode() {
        return this.isGestureMode;
    }

    public void setGestureMode(boolean z) {
        this.isGestureMode = z;
    }

    public boolean isTurn180() {
        return this.isTurn180;
    }

    public void setTurn180(boolean z) {
        this.isTurn180 = z;
    }

    public boolean isMenuOpen() {
        return this.isMenuOpen;
    }

    public void setMenuOpen(boolean z) {
        this.isMenuOpen = z;
    }

    public void setItemList(List<String> list, Map<String, Integer> map) {
        this.itemList = list;
        this.resMap = map;
    }

    public TopListViewAdapter(Context context, List<String> list, Map<String, Integer> map) {
        this.mContext = context;
        this.itemList = list;
        this.resMap = map;
    }

    @Override // android.widget.Adapter
    public int getCount() {
        List<String> list = this.itemList;
        if (list == null) {
            return 0;
        }
        return list.size();
    }

    @Override // android.widget.Adapter
    public Object getItem(int i) {
        List<String> list;
        if (i < 0 || (list = this.itemList) == null || i >= list.size()) {
            return null;
        }
        return this.itemList.get(i);
    }

    @Override // android.widget.Adapter
    public View getView(int i, View view, ViewGroup viewGroup) {
        Map<String, Integer> map;
        Integer num;
        ViewHolder viewHolder;
        View view2;
        View view3 = view;
        if (i == 2) {
            if (view == null) {
                View viewInflate = LayoutInflater.from(viewGroup.getContext()).inflate(C3033R.layout.item_top_bar_record, viewGroup, false);
                viewHolder = new ViewHolder();
                viewHolder.imageView = (ImageView) viewInflate.findViewById(C3033R.id.iv_top_bar_item);
                viewHolder.textView = (TextView) viewInflate.findViewById(C3033R.id.device_video_time_tv);
                viewInflate.setTag(viewHolder);
                view2 = viewInflate;
            } else {
                viewHolder = (ViewHolder) view.getTag();
                view2 = view;
            }
            if (this.isRecordVideo) {
                if (viewHolder != null) {
                    viewHolder.imageView.setImageResource(C3033R.mipmap.icon_record_video_yellow);
                    viewHolder.textView.setText(this.timer);
                }
            } else if (viewHolder != null) {
                viewHolder.imageView.setImageResource(C3033R.drawable.drawable_video);
                this.timer = "";
                viewHolder.textView.setText(this.timer);
            }
            return view2;
        }
        if (view == null) {
            ImageView imageView = new ImageView(this.mContext);
            imageView.setLayoutParams(new ViewGroup.LayoutParams(AppUtils.dip2px(this.mContext, 45.0f), AppUtils.dip2px(this.mContext, 45.0f)));
            imageView.setScaleType(ImageView.ScaleType.FIT_XY);
            view3 = imageView;
        }
        String str = (String) getItem(i);
        if (!TextUtils.isEmpty(str) && (map = this.resMap) != null && (num = map.get(str)) != null) {
            if (num.intValue() == C3033R.mipmap.icon_control_model_on || num.intValue() == C3033R.mipmap.icon_control_model_off) {
                if (this.isControlMode) {
                    ((ImageView) view3).setImageResource(C3033R.mipmap.icon_control_model_on);
                } else {
                    ((ImageView) view3).setImageResource(C3033R.mipmap.icon_control_model_off);
                }
            } else if (num.intValue() == C3033R.mipmap.icon_power_30 || num.intValue() == C3033R.mipmap.icon_power_60 || num.intValue() == C3033R.mipmap.icon_power_100) {
                if (getCurrPower() == 4) {
                    ((ImageView) view3).setImageResource(C3033R.mipmap.icon_power_30);
                } else if (getCurrPower() == 9) {
                    ((ImageView) view3).setImageResource(C3033R.mipmap.icon_power_60);
                } else if (getCurrPower() == 14) {
                    ((ImageView) view3).setImageResource(C3033R.mipmap.icon_power_100);
                }
            } else if (num.intValue() == C3033R.drawable.drawable_gesture_recognition_close || num.intValue() == C3033R.drawable.drawable_gesture_recognition_open) {
                if (this.isGestureMode) {
                    ((ImageView) view3).setImageResource(C3033R.drawable.drawable_gesture_recognition_open);
                } else {
                    ((ImageView) view3).setImageResource(C3033R.drawable.drawable_gesture_recognition_close);
                }
            } else if (num.intValue() == C3033R.drawable.drawable_fixed_height || num.intValue() == C3033R.drawable.drawable_fixed_height_yellow) {
                if (this.isFixedHeightMode) {
                    ((ImageView) view3).setImageResource(C3033R.drawable.drawable_fixed_height_yellow);
                } else {
                    ((ImageView) view3).setImageResource(C3033R.drawable.drawable_fixed_height);
                }
            } else if (num.intValue() == C3033R.drawable.drawable_turn_screen_icon || num.intValue() == C3033R.drawable.drawable_turn_screen_yellow) {
                ((ImageView) view3).setImageResource(C3033R.drawable.drawable_turn_screen_icon);
            } else if (num.intValue() == C3033R.drawable.drawable_down_menu || num.intValue() == C3033R.drawable.drawable_down_menu_yellow) {
                if (this.isMenuOpen) {
                    ((ImageView) view3).setImageResource(C3033R.drawable.drawable_down_menu_yellow);
                } else {
                    ((ImageView) view3).setImageResource(C3033R.drawable.drawable_down_menu);
                }
            } else {
                ((ImageView) view3).setImageResource(num.intValue());
            }
        }
        return view3;
    }
}
