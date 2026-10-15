package com.cooingdv.rcufo.fragment;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListAdapter;
import android.widget.ListView;
import android.widget.TextView;
import androidx.core.view.ViewCompat;
import com.cooingdv.rcufo.BuildConfig;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.activity.ConnectionRecordsActivity;
import com.cooingdv.rcufo.activity.MainActivity;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.base.MainApplication;
import com.cooingdv.rcufo.beans.DeviceInfo;
import com.cooingdv.rcufo.dialog.DeviceListDialog;
import com.cooingdv.rcufo.dialog.SelectLanguageDialog;
import com.cooingdv.rcufo.socket.SocketClient;
import com.cooingdv.rcufo.tools.BufChangeHex;
import com.cooingdv.rcufo.tools.GoogleMobileAdsConsentManager;
import com.cooingdv.rcufo.tools.IActions;
import com.cooingdv.rcufo.tools.IConstants;
import com.cooingdv.rcufo.tools.PreferencesHelper;
import com.cooingdv.rcufo.utils.AppUtils;
import com.cooingdv.rcufo.utils.Dbug;
import com.cooingdv.rcufo.utils.LocalUtil;
import com.google.android.ump.ConsentForm;
import com.google.android.ump.FormError;
import com.inuker.bluetooth.library.BluetoothClient;
import com.inuker.bluetooth.library.beacon.Beacon;
import com.inuker.bluetooth.library.beacon.BeaconItem;
import com.inuker.bluetooth.library.connect.listener.BluetoothStateListener;
import com.inuker.bluetooth.library.search.SearchRequest;
import com.inuker.bluetooth.library.search.SearchResult;
import com.inuker.bluetooth.library.search.response.SearchResponse;
import com.inuker.bluetooth.library.utils.ByteUtils;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/* JADX INFO: loaded from: classes2.dex */
public class SettingsFragment extends BaseFragment implements AdapterView.OnItemClickListener, SelectLanguageDialog.OnSelectLanguageListener {
    private boolean isViewPassword;
    private BluetoothClient mClient;
    private DeviceListDialog mDeviceListDialog;
    private MyBroadcastReceiver mReceiver;
    private SettingsAdapter settingsAdapter;
    private ListView settingsListView;
    private String mAppVersion = "";
    private List<DeviceInfo> mList = new ArrayList();
    private int mUsedSpace = -1;
    private int mTotalSpace = -1;
    private String address = "";
    private final BluetoothStateListener mBluetoothStateListener = new BluetoothStateListener() { // from class: com.cooingdv.rcufo.fragment.SettingsFragment.1
        @Override // com.inuker.bluetooth.library.connect.listener.BluetoothStateListener
        public void onBluetoothStateChanged(boolean z) {
            SettingsFragment.this.searchBlueTooth();
            SettingsFragment.this.mClient.unregisterBluetoothStateListener(SettingsFragment.this.mBluetoothStateListener);
        }
    };

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_settings, viewGroup, false);
        ListView listView = (ListView) viewInflate.findViewById(C3033R.id.settings_list_view);
        this.settingsListView = listView;
        listView.setOnItemClickListener(this);
        return viewInflate;
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        super.onActivityCreated(bundle);
        if (getActivity() != null) {
            initListView();
            this.mAppVersion = "V" + getVersion();
            this.mClient = new BluetoothClient(getActivity());
        }
    }

    private static String getVersion() {
        return BuildConfig.VERSION_NAME;
    }

    @Override // androidx.fragment.app.Fragment
    public void onStart() {
        super.onStart();
        this.mReceiver = new MyBroadcastReceiver();
        IntentFilter intentFilter = new IntentFilter();
        intentFilter.addAction(IActions.ACTION_CHANGE_LANGUAGE);
        if (Build.VERSION.SDK_INT >= 26) {
            MainApplication.getInstance().registerReceiver(this.mReceiver, intentFilter, 2);
        } else {
            MainApplication.getInstance().registerReceiver(this.mReceiver, intentFilter);
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onResume() {
        super.onResume();
        SocketClient.getInstance().setActivity(getActivity());
    }

    @Override // androidx.fragment.app.Fragment
    public void onPause() {
        super.onPause();
        SocketClient.getInstance().setActivity(null);
    }

    @Override // androidx.fragment.app.Fragment
    public void onStop() {
        super.onStop();
        if (this.mReceiver != null) {
            MainApplication.getInstance().unregisterReceiver(this.mReceiver);
        }
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
    }

    @Override // android.widget.AdapterView.OnItemClickListener
    public void onItemClick(AdapterView<?> adapterView, View view, int i, long j) {
        SettingsAdapter settingsAdapter = this.settingsAdapter;
        if (settingsAdapter != null) {
            String str = (String) settingsAdapter.getItem(i);
            if (TextUtils.isEmpty(str)) {
                return;
            }
            if (str.equals(getString(C3033R.string.app_declare))) {
                GoogleMobileAdsConsentManager.getInstance(getActivity().getApplicationContext()).showPrivacyOptionsForm(getActivity(), new ConsentForm.OnConsentFormDismissedListener() { // from class: com.cooingdv.rcufo.fragment.SettingsFragment$$ExternalSyntheticLambda0
                    @Override // com.google.android.ump.ConsentForm.OnConsentFormDismissedListener
                    public final void onConsentFormDismissed(FormError formError) {
                        SettingsFragment.lambda$onItemClick$0(formError);
                    }
                });
                return;
            }
            if (str.equals(getString(C3033R.string.language_setting))) {
                showSelectLanguageDialog(PreferencesHelper.getSharedPreferences(getActivity().getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(getActivity())));
                return;
            }
            if (str.equals(getString(C3033R.string.icp_number))) {
                Intent intent = new Intent();
                intent.setAction("android.intent.action.VIEW");
                intent.setData(Uri.parse("https://beian.miit.gov.cn"));
                startActivity(intent);
                return;
            }
            if (str.equals(getString(C3033R.string.view_password))) {
                if (SocketClient.getInstance().isActive()) {
                    showShortToast(getString(C3033R.string.connected_device_tip));
                    return;
                } else {
                    checkOpenBlueTooth();
                    return;
                }
            }
            if (str.equals(getString(C3033R.string.change_password))) {
                if (!SocketClient.getInstance().isActive()) {
                    showShortToast(getString(C3033R.string.connect_device_tip));
                    return;
                } else if (SocketClient.getInstance().isChangePassword()) {
                    showShortToast(getString(C3033R.string.password_changed_successfully));
                    return;
                } else {
                    SocketClient.getInstance().changePassword(getActivity());
                    return;
                }
            }
            if (str.equals(getString(C3033R.string.connection_record))) {
                startActivity(new Intent(getActivity(), (Class<?>) ConnectionRecordsActivity.class));
            }
        }
    }

    static /* synthetic */ void lambda$onItemClick$0(FormError formError) {
        if (formError != null) {
            Dbug.m13286i("UNAD_SDK", "onConsentFormDismissed:" + formError.getMessage());
        }
    }

    private void checkOpenBlueTooth() {
        if (Build.VERSION.SDK_INT >= 31) {
            requestPermission(new String[]{"android.permission.BLUETOOTH_CONNECT", "android.permission.BLUETOOTH_SCAN", "android.permission.ACCESS_FINE_LOCATION"}, 4);
        } else {
            requestPermission(new String[]{"android.permission.ACCESS_FINE_LOCATION"}, 3);
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void searchBlueTooth() {
        if (this.isViewPassword) {
            return;
        }
        this.mClient.search(new SearchRequest.Builder().searchBluetoothLeDevice(3000, 3).build(), new SearchResponse() { // from class: com.cooingdv.rcufo.fragment.SettingsFragment.2
            @Override // com.inuker.bluetooth.library.search.response.SearchResponse
            public void onSearchStarted() {
                Dbug.m13286i(SettingsFragment.this.TAG, "connectWifi onSearchStarted");
                SettingsFragment.this.isViewPassword = true;
                SettingsFragment.this.mList.clear();
            }

            @Override // com.inuker.bluetooth.library.search.response.SearchResponse
            public void onDeviceFounded(SearchResult searchResult) {
                Beacon beacon = new Beacon(searchResult.scanRecord);
                String name = searchResult.getName();
                Dbug.m13286i(SettingsFragment.this.TAG, "connectWifi deviceName{" + name + "}");
                if (name.contains("WIFIPD")) {
                    SettingsFragment.this.mClient.stopSearch();
                    SettingsFragment.this.address = searchResult.getAddress();
                    String string = "";
                    String string2 = "";
                    for (BeaconItem beaconItem : beacon.mItems) {
                        if (beaconItem.type == 22) {
                            byte[] bArr = beaconItem.bytes;
                            StringBuilder sb = new StringBuilder();
                            StringBuilder sb2 = new StringBuilder();
                            try {
                                for (byte b : bArr) {
                                    String strByteToHex = BufChangeHex.byteToHex(b);
                                    if (strByteToHex.equals("FF") || strByteToHex.equals("ff")) {
                                        break;
                                        break;
                                    }
                                    sb2.append(String.format("%c", Integer.valueOf(b & 255)));
                                }
                                sb.append(sb2.toString());
                            } catch (Exception unused) {
                                sb.append(ByteUtils.byteToString(bArr));
                            }
                            string = sb.toString();
                        } else if (beaconItem.type == 255) {
                            byte[] bArr2 = beaconItem.bytes;
                            if (Integer.parseInt(BufChangeHex.byteToHex(bArr2[0]), 16) == 255) {
                                StringBuilder sb3 = new StringBuilder();
                                StringBuilder sb4 = new StringBuilder();
                                for (int i = 1; i < 9; i++) {
                                    try {
                                        sb4.append(String.format("%c", Integer.valueOf(bArr2[i] & 255)));
                                    } catch (Exception unused2) {
                                        sb3.append(ByteUtils.byteToString(bArr2));
                                    }
                                }
                                sb3.append(sb4.toString());
                                string2 = sb3.toString();
                            }
                        }
                    }
                    DeviceInfo deviceInfo = new DeviceInfo();
                    deviceInfo.setWifiName(string);
                    deviceInfo.setWifiPassword(string2);
                    SettingsFragment.this.mList.add(deviceInfo);
                    Dbug.m13286i(SettingsFragment.this.TAG, "connectWifi {" + string + "},{" + string2 + "},{" + BufChangeHex.getMacAddressReversed(SettingsFragment.this.address) + "}");
                }
            }

            @Override // com.inuker.bluetooth.library.search.response.SearchResponse
            public void onSearchStopped() {
                Dbug.m13286i(SettingsFragment.this.TAG, "connectWifi onSearchStopped");
                SettingsFragment.this.isViewPassword = false;
                if (SettingsFragment.this.mList == null || SettingsFragment.this.mList.size() <= 0) {
                    return;
                }
                if (SettingsFragment.this.mDeviceListDialog == null) {
                    SettingsFragment.this.mDeviceListDialog = new DeviceListDialog(SettingsFragment.this.mList);
                }
                if (!SettingsFragment.this.mDeviceListDialog.isShowing()) {
                    SettingsFragment.this.mDeviceListDialog.show(SettingsFragment.this.getActivity().getFragmentManager(), "DEVICE_WIFI_LIST");
                }
                Dbug.m13286i(SettingsFragment.this.TAG, "mList = " + SettingsFragment.this.mList);
            }

            @Override // com.inuker.bluetooth.library.search.response.SearchResponse
            public void onSearchCanceled() {
                Dbug.m13286i(SettingsFragment.this.TAG, "connectWifi onSearchCanceled");
                SettingsFragment.this.isViewPassword = false;
                if (SettingsFragment.this.mList == null || SettingsFragment.this.mList.size() <= 0) {
                    return;
                }
                if (SettingsFragment.this.mDeviceListDialog == null) {
                    SettingsFragment.this.mDeviceListDialog = new DeviceListDialog(SettingsFragment.this.mList);
                }
                if (!SettingsFragment.this.mDeviceListDialog.isShowing()) {
                    SettingsFragment.this.mDeviceListDialog.show(SettingsFragment.this.getActivity().getFragmentManager(), "DEVICE_WIFI_LIST");
                }
                Dbug.m13286i(SettingsFragment.this.TAG, "mList = " + SettingsFragment.this.mList);
            }
        });
    }

    @Override // com.cooingdv.rcufo.base.BaseFragment
    public void permissionSuccess(int i) {
        if (i == 3 || i == 4) {
            if (!this.mClient.isBluetoothOpened()) {
                this.mClient.registerBluetoothStateListener(this.mBluetoothStateListener);
                this.mClient.openBluetooth();
            } else {
                searchBlueTooth();
            }
        }
    }

    private void initListView() {
        String[] stringArray;
        int i;
        if (getActivity() != null) {
            if (MainApplication.getInstance().isGoogle()) {
                if (GoogleMobileAdsConsentManager.getInstance(getActivity()).isPrivacyOptionsRequired()) {
                    stringArray = getResources().getStringArray(C3033R.array.settings_list_google_privacy);
                } else {
                    stringArray = getResources().getStringArray(C3033R.array.settings_list_google);
                }
            } else if (PreferencesHelper.getSharedPreferences(getActivity().getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(getActivity())) == 0) {
                if (SocketClient.getInstance().isActive() && SocketClient.getInstance().isPasswordCorrect()) {
                    stringArray = getResources().getStringArray(C3033R.array.settings_list_password);
                } else {
                    stringArray = getResources().getStringArray(C3033R.array.settings_list);
                }
            } else {
                stringArray = getResources().getStringArray(C3033R.array.settings_list_password);
            }
            ArrayList<String> arrayList = new ArrayList();
            Collections.addAll(arrayList, stringArray);
            HashMap map = new HashMap();
            for (String str : arrayList) {
                if (!TextUtils.isEmpty(str)) {
                    if (str.equals(getString(C3033R.string.right_hand_mode))) {
                        i = 0;
                    } else {
                        i = (str.equals(getString(C3033R.string.sd_card_storage)) || str.equals(getString(C3033R.string.app_version)) || str.equals(getString(C3033R.string.language_setting)) || str.equals(getString(C3033R.string.app_declare)) || str.equals(getString(C3033R.string.icp_number)) || str.equals(getString(C3033R.string.view_password)) || str.equals(getString(C3033R.string.change_password)) || str.equals(getString(C3033R.string.connection_record))) ? 1 : -1;
                    }
                    if (i != -1) {
                        map.put(str, Integer.valueOf(i));
                    }
                }
            }
            SettingsAdapter settingsAdapter = new SettingsAdapter(getActivity().getApplicationContext());
            this.settingsAdapter = settingsAdapter;
            this.settingsListView.setAdapter((ListAdapter) settingsAdapter);
            this.settingsAdapter.setItemList(arrayList, map);
        }
    }

    private void showSelectLanguageDialog(int i) {
        if (getActivity() != null) {
            SelectLanguageDialog selectLanguageDialog = new SelectLanguageDialog();
            selectLanguageDialog.setLanguageFlag(i);
            selectLanguageDialog.setOnSelectLanguageListener(this);
            selectLanguageDialog.show(getActivity().getFragmentManager(), "select_language_dialog");
        }
    }

    @Override // com.cooingdv.rcufo.dialog.SelectLanguageDialog.OnSelectLanguageListener
    public void onSelectLanguage(int i) {
        if (PreferencesHelper.getSharedPreferences(getActivity().getApplicationContext()).getInt(IConstants.KEY_LANGUAGE_FLAG, LocalUtil.getLocaleLanguage(getActivity())) != i) {
            Locale language = AppUtils.getLanguage(i);
            if (language != null) {
                AppUtils.setLanguage(getActivity().getApplicationContext(), language);
                PreferencesHelper.putIntValue(getActivity().getApplicationContext(), IConstants.KEY_LANGUAGE_FLAG, i);
                getActivity().sendBroadcast(new Intent(IActions.ACTION_CHANGE_LANGUAGE));
                return;
            }
            return;
        }
        showShortToast(C3033R.string.language_no_change);
    }

    private class MyBroadcastReceiver extends BroadcastReceiver {
        private MyBroadcastReceiver() {
        }

        @Override // android.content.BroadcastReceiver
        public void onReceive(Context context, Intent intent) {
            if (context == null || intent == null) {
                return;
            }
            String action = intent.getAction();
            if (TextUtils.isEmpty(action)) {
                return;
            }
            action.hashCode();
            if (action.equals(IActions.ACTION_CHANGE_LANGUAGE) && SettingsFragment.this.getActivity() != null) {
                SettingsFragment.this.startActivity(new Intent(SettingsFragment.this.getActivity(), (Class<?>) MainActivity.class));
                SettingsFragment.this.getActivity().finish();
            }
        }
    }

    private class SettingsAdapter extends BaseAdapter {
        private List<String> itemList = new ArrayList();
        private Context mContext;
        private SharedPreferences sharedPreferences;
        private Map<String, Integer> typeMap;

        @Override // android.widget.Adapter
        public long getItemId(int i) {
            return i;
        }

        @Override // android.widget.BaseAdapter, android.widget.Adapter
        public int getViewTypeCount() {
            return 3;
        }

        SettingsAdapter(Context context) {
            this.mContext = context;
            this.sharedPreferences = PreferencesHelper.getSharedPreferences(this.mContext);
        }

        void setItemList(List<String> list, Map<String, Integer> map) {
            if (list != null) {
                this.itemList = list;
            }
            if (map != null) {
                this.typeMap = map;
            }
            notifyDataSetChanged();
        }

        @Override // android.widget.BaseAdapter, android.widget.Adapter
        public int getItemViewType(int i) {
            Map<String, Integer> map;
            Integer num;
            String str = (String) getItem(i);
            if (TextUtils.isEmpty(str) || (map = this.typeMap) == null || (num = map.get(str)) == null) {
                return 2;
            }
            return num.intValue();
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
            final ViewHolder viewHolder;
            ViewHolder1 viewHolder1;
            String str = (String) getItem(i);
            int itemViewType = getItemViewType(i);
            if (itemViewType == 0) {
                if (view == null) {
                    view = LayoutInflater.from(this.mContext).inflate(C3033R.layout.item_settings_one, viewGroup, false);
                    viewHolder = new ViewHolder();
                    viewHolder.f10179tv = (TextView) view.findViewById(C3033R.id.item_settings_one_tv);
                    viewHolder.tv1 = (TextView) view.findViewById(C3033R.id.item_settings_one_switch_tv1);
                    viewHolder.tv2 = (TextView) view.findViewById(C3033R.id.item_settings_one_switch_tv2);
                    view.setTag(viewHolder);
                } else {
                    viewHolder = (ViewHolder) view.getTag();
                }
                if (!TextUtils.isEmpty(str)) {
                    viewHolder.f10179tv.setText(str);
                    if (str.equals(SettingsFragment.this.getString(C3033R.string.right_hand_mode))) {
                        viewHolder.tv1.setText(SettingsFragment.this.getString(C3033R.string.shutdown));
                        viewHolder.tv2.setText(SettingsFragment.this.getString(C3033R.string.open));
                        if (this.sharedPreferences.getBoolean(IConstants.RIGHT_HAND_MODE, false)) {
                            viewHolder.tv2.setSelected(true);
                            SettingsFragment.this.switchTextView(2, viewHolder.tv2, viewHolder.tv1, null, null, null);
                        } else {
                            viewHolder.tv1.setSelected(true);
                        }
                        viewHolder.tv1.setOnClickListener(new View.OnClickListener() { // from class: com.cooingdv.rcufo.fragment.SettingsFragment.SettingsAdapter.1
                            @Override // android.view.View.OnClickListener
                            public void onClick(View view2) {
                                if (!view2.isSelected() && SettingsAdapter.this.sharedPreferences.getBoolean(IConstants.RIGHT_HAND_MODE, false)) {
                                    view2.setSelected(true);
                                    viewHolder.tv2.setSelected(false);
                                    PreferencesHelper.putBooleanValue(SettingsAdapter.this.mContext, IConstants.RIGHT_HAND_MODE, false);
                                    SettingsFragment.this.switchTextView(0, viewHolder.tv1, viewHolder.tv2, null, null, null);
                                    SettingsFragment.this.getActivity().sendBroadcast(new Intent(IActions.ACTION_CHANGE_LANGUAGE));
                                }
                            }
                        });
                        viewHolder.tv2.setOnClickListener(new View.OnClickListener() { // from class: com.cooingdv.rcufo.fragment.SettingsFragment.SettingsAdapter.2
                            @Override // android.view.View.OnClickListener
                            public void onClick(View view2) {
                                if (view2.isSelected() || SettingsAdapter.this.sharedPreferences.getBoolean(IConstants.RIGHT_HAND_MODE, false)) {
                                    return;
                                }
                                view2.setSelected(true);
                                viewHolder.tv1.setSelected(false);
                                PreferencesHelper.putBooleanValue(SettingsAdapter.this.mContext, IConstants.RIGHT_HAND_MODE, true);
                                SettingsFragment.this.switchTextView(2, viewHolder.tv2, viewHolder.tv1, null, null, null);
                                SettingsFragment.this.getActivity().sendBroadcast(new Intent(IActions.ACTION_CHANGE_LANGUAGE));
                            }
                        });
                    }
                }
            } else if (itemViewType == 1) {
                if (view == null) {
                    view = LayoutInflater.from(this.mContext).inflate(C3033R.layout.item_settings_two, viewGroup, false);
                    viewHolder1 = new ViewHolder1();
                    viewHolder1.f10180tv = (TextView) view.findViewById(C3033R.id.item_settings_two_tv);
                    viewHolder1.tv1 = (TextView) view.findViewById(C3033R.id.item_settings_two_tv_1);
                    viewHolder1.tv2 = (TextView) view.findViewById(C3033R.id.item_settings_two_switch_tv1);
                    viewHolder1.tv3 = (TextView) view.findViewById(C3033R.id.item_settings_two_switch_tv2);
                    viewHolder1.icon = (ImageView) view.findViewById(C3033R.id.item_settings_two_icon);
                    viewHolder1.layout = (LinearLayout) view.findViewById(C3033R.id.item_settings_two_switch_layout);
                    view.setTag(viewHolder1);
                } else {
                    viewHolder1 = (ViewHolder1) view.getTag();
                }
                if (!TextUtils.isEmpty(str)) {
                    viewHolder1.f10180tv.setText(str);
                    viewHolder1.icon.setVisibility(8);
                    viewHolder1.tv1.setVisibility(8);
                    viewHolder1.layout.setVisibility(8);
                    if (str.equals(SettingsFragment.this.getString(C3033R.string.app_version))) {
                        viewHolder1.tv1.setText(SettingsFragment.this.mAppVersion);
                        viewHolder1.tv1.setVisibility(0);
                    } else if (str.equals(SettingsFragment.this.getString(C3033R.string.sd_card_storage))) {
                        if (SettingsFragment.this.mUsedSpace < 0 || SettingsFragment.this.mTotalSpace <= 0) {
                            viewHolder1.tv1.setText("");
                        } else {
                            viewHolder1.tv1.setText(String.format(Locale.US, "%.2fG/%.2fG", Float.valueOf(SettingsFragment.this.mUsedSpace / 1024.0f), Float.valueOf(SettingsFragment.this.mTotalSpace / 1024.0f)));
                        }
                        viewHolder1.tv1.setText(AppUtils.getSDAvailableSize(SettingsFragment.this.getContext()) + "/" + AppUtils.getSDTotalSize(SettingsFragment.this.getContext()));
                        viewHolder1.tv1.setVisibility(0);
                    }
                }
            }
            return view;
        }

        private class ViewHolder {

            /* JADX INFO: renamed from: tv */
            private TextView f10179tv;
            private TextView tv1;
            private TextView tv2;

            private ViewHolder() {
            }
        }

        private class ViewHolder1 {
            private ImageView icon;
            private LinearLayout layout;

            /* JADX INFO: renamed from: tv */
            private TextView f10180tv;
            private TextView tv1;
            private TextView tv2;
            private TextView tv3;

            private ViewHolder1() {
            }
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void switchTextView(int i, TextView textView, TextView textView2, TextView textView3, TextView textView4, TextView textView5) {
        if (i == 0) {
            textView.setBackgroundResource(C3033R.drawable.bg_switch_left_settings);
        } else if (i == 1) {
            textView.setBackgroundColor(-1);
        } else {
            textView.setBackgroundResource(C3033R.drawable.bg_switch_right_settings);
        }
        textView.setTextColor(ViewCompat.MEASURED_STATE_MASK);
        textView2.setTextColor(-1);
        textView2.setBackgroundColor(0);
        if (textView3 != null) {
            textView3.setTextColor(-1);
            textView3.setBackgroundColor(0);
        }
        if (textView4 != null) {
            textView4.setTextColor(-1);
            textView4.setBackgroundColor(0);
        }
        if (textView5 != null) {
            textView5.setTextColor(-1);
            textView5.setBackgroundColor(0);
        }
    }
}
