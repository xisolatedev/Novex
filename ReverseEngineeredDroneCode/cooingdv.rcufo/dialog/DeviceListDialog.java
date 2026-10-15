package com.cooingdv.rcufo.dialog;

import android.content.Context;
import android.os.Bundle;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.ImageView;
import android.widget.ListAdapter;
import android.widget.ListView;
import android.widget.TextView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseDialogFragment;
import com.cooingdv.rcufo.beans.DeviceInfo;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class DeviceListDialog extends BaseDialogFragment implements View.OnClickListener, AdapterView.OnItemClickListener {
    private List<DeviceInfo> data;
    private ListView deviceListView;
    private DeviceListAdapter mAdapter;
    private OnDeviceListDialogListener onDeviceListDialogListener;

    public interface OnDeviceListDialogListener {
        void onClose();

        void onSelected(int i, DeviceInfo deviceInfo);
    }

    @Override // android.widget.AdapterView.OnItemClickListener
    public void onItemClick(AdapterView<?> adapterView, View view, int i, long j) {
    }

    public void setOnDeviceListDialogListener(OnDeviceListDialogListener onDeviceListDialogListener) {
        this.onDeviceListDialogListener = onDeviceListDialogListener;
    }

    public DeviceListDialog(List<DeviceInfo> list) {
        this.data = list;
    }

    public void setDatas(List<DeviceInfo> list) {
        DeviceListAdapter deviceListAdapter = this.mAdapter;
        if (deviceListAdapter != null) {
            deviceListAdapter.setItemList(list);
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setCancelable(false);
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.dialog_device_list, viewGroup, false);
        if (getDialog() != null) {
            getDialog().requestWindowFeature(1);
        }
        ImageView imageView = (ImageView) viewInflate.findViewById(C3033R.id.dialog_device_list_close_btn);
        this.deviceListView = (ListView) viewInflate.findViewById(C3033R.id.dialog_device_list_view);
        imageView.setOnClickListener(this);
        this.deviceListView.setOnItemClickListener(this);
        return viewInflate;
    }

    @Override // com.cooingdv.rcufo.base.BaseDialogFragment, android.app.DialogFragment, android.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() == null || getDialog() == null || getDialog().getWindow() == null) {
            return;
        }
        initListView();
        WindowManager.LayoutParams attributes = getDialog().getWindow().getAttributes();
        attributes.width = 200;
        attributes.height = 200;
        DisplayMetrics displayMetrics = getResources().getDisplayMetrics();
        if (getResources().getConfiguration().orientation == 2) {
            attributes.width = (displayMetrics.heightPixels * 5) / 6;
            attributes.height = (displayMetrics.heightPixels * 5) / 6;
        } else if (getResources().getConfiguration().orientation == 1) {
            attributes.width = (displayMetrics.widthPixels * 5) / 6;
            attributes.height = (displayMetrics.widthPixels * 5) / 6;
        }
        attributes.gravity = 17;
        getDialog().getWindow().setAttributes(attributes);
        getDialog().getWindow().setBackgroundDrawableResource(C3033R.drawable.bg_dialog);
    }

    @Override // android.view.View.OnClickListener
    public void onClick(View view) {
        if (getActivity() == null || getDialog() == null || view == null || view.getId() != C3033R.id.dialog_device_list_close_btn) {
            return;
        }
        OnDeviceListDialogListener onDeviceListDialogListener = this.onDeviceListDialogListener;
        if (onDeviceListDialogListener != null) {
            onDeviceListDialogListener.onClose();
        }
        dismiss();
    }

    private void initListView() {
        if (getActivity() == null || getDialog() == null) {
            return;
        }
        DeviceListAdapter deviceListAdapter = new DeviceListAdapter(getActivity(), this.data);
        this.mAdapter = deviceListAdapter;
        this.deviceListView.setAdapter((ListAdapter) deviceListAdapter);
    }

    private class DeviceListAdapter extends BaseAdapter {
        private List<DeviceInfo> itemList;
        private Context mContext;

        @Override // android.widget.Adapter
        public long getItemId(int i) {
            return i;
        }

        DeviceListAdapter(Context context, List<DeviceInfo> list) {
            this.mContext = context;
            this.itemList = list;
        }

        public void setItemList(List<DeviceInfo> list) {
            if (list != null) {
                this.itemList.clear();
                this.itemList.addAll(list);
                notifyDataSetChanged();
            }
        }

        @Override // android.widget.Adapter
        public int getCount() {
            return this.itemList.size();
        }

        @Override // android.widget.Adapter
        public Object getItem(int i) {
            if (i < 0 || i >= this.itemList.size()) {
                return null;
            }
            return this.itemList.get(i);
        }

        @Override // android.widget.Adapter
        public View getView(int i, View view, ViewGroup viewGroup) {
            ViewHolder viewHolder;
            if (view == null) {
                view = LayoutInflater.from(this.mContext).inflate(C3033R.layout.item_device_list, viewGroup, false);
                viewHolder = new ViewHolder();
                viewHolder.tvSSID = (TextView) view.findViewById(C3033R.id.item_device_list_ssid);
                viewHolder.tvBSSID = (TextView) view.findViewById(C3033R.id.item_device_list_bssid);
                view.setTag(viewHolder);
            } else {
                viewHolder = (ViewHolder) view.getTag();
            }
            DeviceInfo deviceInfo = (DeviceInfo) getItem(i);
            if (deviceInfo != null) {
                String wifiName = deviceInfo.getWifiName();
                if (!TextUtils.isEmpty(wifiName)) {
                    viewHolder.tvSSID.setText(wifiName);
                } else {
                    viewHolder.tvSSID.setText("unknown");
                }
                viewHolder.tvBSSID.setText(deviceInfo.getWifiPassword());
            }
            return view;
        }

        private class ViewHolder {
            private TextView tvBSSID;
            private TextView tvSSID;

            private ViewHolder() {
            }
        }
    }
}
