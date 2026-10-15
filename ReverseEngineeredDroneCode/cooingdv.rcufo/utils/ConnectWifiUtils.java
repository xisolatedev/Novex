package com.cooingdv.rcufo.utils;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.ConnectivityManager;
import android.net.MacAddress;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.wifi.WifiConfiguration;
import android.net.wifi.WifiManager;
import android.net.wifi.WifiNetworkSuggestion;
import android.os.Build;
import android.text.TextUtils;
import android.util.Log;
import java.util.ArrayList;
import org.json.C8746w8;

/* JADX INFO: loaded from: classes2.dex */
public class ConnectWifiUtils {
    private static final String TAG = "ConnectWifiUtils";
    private static volatile ConnectWifiUtils mInstance;
    private final ConnectivityManager connectivityManager;
    private final Context mContext;
    private WifiConnectCallback wifiConnectCallback;
    private final WifiManager wifiManager;

    public enum WifiCapability {
        WIFI_CIPHER_WEP,
        WIFI_CIPHER_WPA,
        WIFI_CIPHER_NO_PASS
    }

    public interface WifiConnectCallback {
        void onFailure();

        void onSuccess(Network network);
    }

    public ConnectWifiUtils(Context context) {
        this.mContext = context;
        this.wifiManager = (WifiManager) context.getSystemService(C8746w8.f19407b);
        this.connectivityManager = (ConnectivityManager) context.getSystemService("connectivity");
    }

    public static ConnectWifiUtils initialize(Context context) {
        if (mInstance == null) {
            synchronized (ConnectWifiUtils.class) {
                if (mInstance == null) {
                    mInstance = new ConnectWifiUtils(context);
                }
            }
        }
        return mInstance;
    }

    public void setWifiConnectCallback(WifiConnectCallback wifiConnectCallback) {
        this.wifiConnectCallback = wifiConnectCallback;
    }

    public void connectWifi(String str, String str2, String str3) {
        if (Build.VERSION.SDK_INT >= 29) {
            connectByNew(str, str2, str3);
        } else {
            connectWifiApByNameAndPwd(str, str2);
        }
    }

    private void connectByNew(String str, String str2, String str3) {
        this.connectivityManager.requestNetwork(new NetworkRequest.Builder().addTransportType(1).removeCapability(12).addCapability(13).setNetworkSpecifier(AppUtils$$ExternalSyntheticApiModelOutline0.m13272m().setSsid(str).setWpa2Passphrase(str2).setBssid(MacAddress.fromString(str3)).build()).build(), new ConnectivityManager.NetworkCallback() { // from class: com.cooingdv.rcufo.utils.ConnectWifiUtils.1
            @Override // android.net.ConnectivityManager.NetworkCallback
            public void onAvailable(Network network) {
                super.onAvailable(network);
                if (ConnectWifiUtils.this.wifiConnectCallback != null) {
                    ConnectWifiUtils.this.wifiConnectCallback.onSuccess(network);
                    Dbug.m13284d("WifiUtils", "======onAvailable: ====连接成功======");
                }
            }

            @Override // android.net.ConnectivityManager.NetworkCallback
            public void onUnavailable() {
                super.onUnavailable();
                Dbug.m13284d("WifiUtils", "======onAvailable: ====连接失败======");
                if (ConnectWifiUtils.this.wifiConnectCallback != null) {
                    ConnectWifiUtils.this.wifiConnectCallback.onFailure();
                }
            }
        });
    }

    private void connectBySug(String str, String str2) {
        WifiNetworkSuggestion.Builder isAppInteractionRequired = AppUtils$$ExternalSyntheticApiModelOutline0.m13276m().setSsid(str).setIsAppInteractionRequired(true);
        if (!TextUtils.isEmpty(str2)) {
            isAppInteractionRequired.setWpa2Passphrase(str2);
        }
        WifiNetworkSuggestion wifiNetworkSuggestionBuild = isAppInteractionRequired.build();
        ArrayList arrayList = new ArrayList();
        arrayList.add(wifiNetworkSuggestionBuild);
        if (this.wifiManager.addNetworkSuggestions(arrayList) != 0) {
            return;
        }
        Dbug.m13284d(TAG, "======onReceive: ==网络连接状态=111111111===");
        IntentFilter intentFilter = new IntentFilter("android.net.wifi.action.WIFI_NETWORK_SUGGESTION_POST_CONNECTION");
        this.mContext.registerReceiver(new BroadcastReceiver() { // from class: com.cooingdv.rcufo.utils.ConnectWifiUtils.2
            @Override // android.content.BroadcastReceiver
            public void onReceive(Context context, Intent intent) {
                Log.d(ConnectWifiUtils.TAG, "======onReceive: ==网络连接状态====");
                if (intent.getAction().equals("android.net.wifi.action.WIFI_NETWORK_SUGGESTION_POST_CONNECTION")) {
                    if (ConnectWifiUtils.this.wifiConnectCallback != null) {
                        ConnectWifiUtils.this.wifiConnectCallback.onSuccess(null);
                        Dbug.m13284d("WifiUtils", "======onAvailable: ====连接成功======");
                        return;
                    }
                    return;
                }
                Dbug.m13284d("WifiUtils", "======onAvailable: ====连接失败======");
                if (ConnectWifiUtils.this.wifiConnectCallback != null) {
                    ConnectWifiUtils.this.wifiConnectCallback.onFailure();
                }
            }
        }, intentFilter);
    }

    private WifiConfiguration createWifiConfig(String str, String str2, WifiCapability wifiCapability) {
        WifiConfiguration wifiConfiguration = new WifiConfiguration();
        wifiConfiguration.allowedAuthAlgorithms.clear();
        wifiConfiguration.allowedGroupCiphers.clear();
        wifiConfiguration.allowedKeyManagement.clear();
        wifiConfiguration.allowedPairwiseCiphers.clear();
        wifiConfiguration.allowedProtocols.clear();
        wifiConfiguration.SSID = "\"" + str + "\"";
        WifiConfiguration wifiConfigurationIsExist = isExist(str);
        if (wifiConfigurationIsExist != null) {
            this.wifiManager.removeNetwork(wifiConfigurationIsExist.networkId);
            this.wifiManager.saveConfiguration();
        }
        if (wifiCapability == WifiCapability.WIFI_CIPHER_NO_PASS) {
            wifiConfiguration.allowedKeyManagement.set(0);
        } else if (wifiCapability == WifiCapability.WIFI_CIPHER_WEP) {
            wifiConfiguration.hiddenSSID = true;
            wifiConfiguration.wepKeys[0] = "\"" + str2 + "\"";
            wifiConfiguration.allowedAuthAlgorithms.set(0);
            wifiConfiguration.allowedAuthAlgorithms.set(1);
            wifiConfiguration.allowedKeyManagement.set(0);
            wifiConfiguration.wepTxKeyIndex = 0;
        } else if (wifiCapability == WifiCapability.WIFI_CIPHER_WPA) {
            wifiConfiguration.preSharedKey = "\"" + str2 + "\"";
            wifiConfiguration.hiddenSSID = true;
            wifiConfiguration.allowedAuthAlgorithms.set(0);
            wifiConfiguration.allowedGroupCiphers.set(2);
            wifiConfiguration.allowedKeyManagement.set(1);
            wifiConfiguration.allowedPairwiseCiphers.set(1);
            wifiConfiguration.allowedGroupCiphers.set(3);
            wifiConfiguration.allowedPairwiseCiphers.set(2);
            wifiConfiguration.status = 2;
        }
        return wifiConfiguration;
    }

    public static boolean isNetConnected(ConnectivityManager connectivityManager) {
        return connectivityManager.getActiveNetwork() != null;
    }

    public static boolean isWifi(ConnectivityManager connectivityManager) {
        NetworkCapabilities networkCapabilities;
        if (connectivityManager.getActiveNetwork() != null && (networkCapabilities = connectivityManager.getNetworkCapabilities(connectivityManager.getActiveNetwork())) == null) {
            return networkCapabilities.hasTransport(1);
        }
        return false;
    }

    private WifiConfiguration isExist(String str) {
        for (WifiConfiguration wifiConfiguration : this.wifiManager.getConfiguredNetworks()) {
            if (wifiConfiguration.SSID.equals("\"" + str + "\"")) {
                return wifiConfiguration;
            }
        }
        return null;
    }

    private WifiCapability getCipherType(String str) {
        if (str.contains("WEB")) {
            return WifiCapability.WIFI_CIPHER_WEP;
        }
        if (str.contains("PSK")) {
            return WifiCapability.WIFI_CIPHER_WPA;
        }
        if (str.contains("WPS")) {
            return WifiCapability.WIFI_CIPHER_NO_PASS;
        }
        return WifiCapability.WIFI_CIPHER_NO_PASS;
    }

    public static WifiConfiguration createWifiInfo(String str, String str2) {
        WifiConfiguration wifiConfiguration = new WifiConfiguration();
        wifiConfiguration.allowedAuthAlgorithms.clear();
        wifiConfiguration.allowedGroupCiphers.clear();
        wifiConfiguration.allowedKeyManagement.clear();
        wifiConfiguration.allowedPairwiseCiphers.clear();
        wifiConfiguration.allowedProtocols.clear();
        wifiConfiguration.SSID = "\"" + str + "\"";
        if (TextUtils.isEmpty(str2)) {
            wifiConfiguration.allowedKeyManagement.set(0);
            Log.i(TAG, "password is ''");
            return wifiConfiguration;
        }
        wifiConfiguration.preSharedKey = "\"" + str2 + "\"";
        wifiConfiguration.allowedAuthAlgorithms.set(0);
        wifiConfiguration.allowedGroupCiphers.set(2);
        wifiConfiguration.allowedGroupCiphers.set(3);
        wifiConfiguration.allowedKeyManagement.set(1);
        wifiConfiguration.allowedPairwiseCiphers.set(1);
        wifiConfiguration.allowedPairwiseCiphers.set(2);
        wifiConfiguration.allowedProtocols.set(1);
        wifiConfiguration.allowedProtocols.set(0);
        wifiConfiguration.status = 2;
        return wifiConfiguration;
    }

    public void connectWifiApByNameAndPwd(String str, String str2) {
        int iAddNetwork = this.wifiManager.addNetwork(createWifiInfo(str, str2));
        if (iAddNetwork == -1) {
            WifiConnectCallback wifiConnectCallback = this.wifiConnectCallback;
            if (wifiConnectCallback != null) {
                wifiConnectCallback.onFailure();
            }
            Dbug.m13284d("WifiUtils", "======onAvailable: ====连接失败======");
            Dbug.m13286i(TAG, "操作失败,需要您到手机wifi列表中取消对设备连接的保存");
            return;
        }
        if (!this.wifiManager.isWifiEnabled()) {
            this.wifiManager.setWifiEnabled(true);
        }
        if (!this.wifiManager.enableNetwork(iAddNetwork, true)) {
            WifiConnectCallback wifiConnectCallback2 = this.wifiConnectCallback;
            if (wifiConnectCallback2 != null) {
                wifiConnectCallback2.onFailure();
            }
            Dbug.m13284d("WifiUtils", "======onAvailable: ====连接失败======");
            return;
        }
        Dbug.m13284d("WifiUtils", "======onAvailable: ====连接成功======");
        WifiConnectCallback wifiConnectCallback3 = this.wifiConnectCallback;
        if (wifiConnectCallback3 != null) {
            wifiConnectCallback3.onSuccess(null);
        }
    }

    public void disconnectWifi() {
        int networkId = this.wifiManager.getConnectionInfo().getNetworkId();
        if (networkId != -1) {
            this.wifiManager.disableNetwork(networkId);
            this.wifiManager.disconnect();
        }
    }
}
