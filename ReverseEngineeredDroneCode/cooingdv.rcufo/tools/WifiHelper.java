package com.cooingdv.rcufo.tools;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.net.wifi.ScanResult;
import android.net.wifi.WifiConfiguration;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.telephony.TelephonyManager;
import android.text.TextUtils;
import android.text.format.Formatter;
import android.util.Log;
import com.cooingdv.rcufo.utils.Dbug;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import org.json.C8746w8;

/* JADX INFO: loaded from: classes2.dex */
public class WifiHelper {
    public static final String KEY_NONE = "NONE";
    public static final String KEY_WPA = "WPA_PSK";
    public static int WIFI_CONNECTED = 1;
    public static int WIFI_CONNECTING = 0;
    public static int WIFI_CONNECT_FAILED = 2;
    private static WifiHelper instance = null;
    private static String otherWifiSSID = null;
    private static String tag = "WifiHelper";
    private Context mContext;
    private BroadcastReceiver mReceiver = new BroadcastReceiver() { // from class: com.cooingdv.rcufo.tools.WifiHelper.1
        @Override // android.content.BroadcastReceiver
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (action == null || !action.equals("android.net.wifi.WIFI_STATE_CHANGED")) {
                return;
            }
            intent.getIntExtra("wifi_state", 0);
        }
    };
    private WifiManager mWifiManager;
    private WifiManager.WifiLock wifiLock;

    public enum NetState {
        NET_NO,
        NET_2G,
        NET_3G,
        NET_4G,
        NET_WIFI,
        NET_UNKNOWN
    }

    public enum WifiCipherType {
        NONE,
        IEEE8021XEAP,
        WEP,
        WPA,
        WPA2,
        WPAWPA2
    }

    public static WifiHelper getInstance(Context context) {
        if (instance == null) {
            instance = new WifiHelper(context);
        }
        WifiHelper wifiHelper = instance;
        wifiHelper.mContext = context;
        wifiHelper.registerBroadcast();
        return instance;
    }

    private WifiHelper(Context context) {
        if (context != null) {
            this.mWifiManager = (WifiManager) context.getApplicationContext().getSystemService(C8746w8.f19407b);
            startScan();
        }
    }

    public static boolean isNetworkAvailable(Context context) {
        NetworkInfo[] allNetworkInfo;
        if (context == null) {
            Dbug.m13285e(tag, "-isNetworkAvailable- is error, reason : context is empty!");
            return false;
        }
        ConnectivityManager connectivityManager = (ConnectivityManager) context.getSystemService("connectivity");
        if (connectivityManager != null && (allNetworkInfo = connectivityManager.getAllNetworkInfo()) != null) {
            for (NetworkInfo networkInfo : allNetworkInfo) {
                if (networkInfo.getState() == NetworkInfo.State.CONNECTED) {
                    return networkInfo.getType() != 0;
                }
            }
        }
        return false;
    }

    public boolean isOutSideWifi(String str) {
        WifiInfo wifiConnectionInfo = getWifiConnectionInfo();
        if (wifiConnectionInfo == null) {
            return false;
        }
        String ssid = wifiConnectionInfo.getSSID();
        if (TextUtils.isEmpty(ssid)) {
            return false;
        }
        String ssid2 = formatSSID(ssid);
        return !TextUtils.isEmpty(ssid2) && ssid2.startsWith(str);
    }

    public static boolean isNetWorkConnectedType(Context context, int i) {
        ConnectivityManager connectivityManager;
        NetworkInfo[] allNetworkInfo;
        if (context != null && (connectivityManager = (ConnectivityManager) context.getApplicationContext().getSystemService("connectivity")) != null && (allNetworkInfo = connectivityManager.getAllNetworkInfo()) != null) {
            for (NetworkInfo networkInfo : allNetworkInfo) {
                if (networkInfo.getDetailedState() == NetworkInfo.DetailedState.CONNECTED) {
                    return networkInfo.getType() == i;
                }
            }
        }
        return false;
    }

    public int isWifiConnected(Context context) {
        if (context == null) {
            Dbug.m13285e(tag, "-isWifiConnected- is error, reason : context is empty!");
            return -1;
        }
        startScan();
        NetworkInfo networkInfo = ((ConnectivityManager) context.getSystemService("connectivity")).getNetworkInfo(1);
        if (networkInfo.getDetailedState() == NetworkInfo.DetailedState.OBTAINING_IPADDR || networkInfo.getDetailedState() == NetworkInfo.DetailedState.CONNECTING) {
            return WIFI_CONNECTING;
        }
        if (networkInfo.getDetailedState() == NetworkInfo.DetailedState.CONNECTED) {
            return WIFI_CONNECTED;
        }
        Dbug.m13286i(tag, "getDetailedState() == " + networkInfo.getDetailedState());
        return WIFI_CONNECT_FAILED;
    }

    public static String interceptChar0Before(String str) {
        if (str == null) {
            return null;
        }
        char[] charArray = str.toCharArray();
        StringBuilder sb = new StringBuilder();
        for (char c : charArray) {
            if (Character.valueOf(c).hashCode() == 0) {
                break;
            }
            sb.append(c);
        }
        return sb.toString();
    }

    public boolean isWiFiActive(Context context) {
        NetworkInfo[] allNetworkInfo;
        ConnectivityManager connectivityManager = (ConnectivityManager) context.getApplicationContext().getSystemService("connectivity");
        if (connectivityManager != null && (allNetworkInfo = connectivityManager.getAllNetworkInfo()) != null) {
            for (NetworkInfo networkInfo : allNetworkInfo) {
                if (networkInfo.getTypeName().equals("WIFI") && networkInfo.isConnected()) {
                    return true;
                }
            }
        }
        return false;
    }

    public static boolean isWifi(Context context) {
        return isNetworkAvailable(context) && ((ConnectivityManager) context.getSystemService("connectivity")).getActiveNetworkInfo().getType() == 1;
    }

    public boolean isWifiClosed() {
        int wifiState = getWifiState();
        return wifiState == 1 || wifiState == 0;
    }

    public boolean isWifiOpened() {
        int wifiState = getWifiState();
        return wifiState == 3 || wifiState == 2;
    }

    public void openWifi() {
        if (this.mWifiManager == null || !isWifiClosed()) {
            return;
        }
        this.mWifiManager.setWifiEnabled(true);
    }

    public void closeWifi() {
        if (this.mWifiManager == null || !isWifiOpened()) {
            return;
        }
        this.mWifiManager.setWifiEnabled(false);
    }

    public int getWifiState() {
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            return wifiManager.getWifiState();
        }
        return 0;
    }

    public List<WifiConfiguration> getSavedWifiConfiguration() {
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            return wifiManager.getConfiguredNetworks();
        }
        return null;
    }

    public List<ScanResult> getWifiScanResult() {
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            return wifiManager.getScanResults();
        }
        return null;
    }

    public synchronized void startScan() {
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            wifiManager.startScan();
        }
    }

    public void connectionConfiguration(int i) {
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            wifiManager.disconnect();
            this.mWifiManager.enableNetwork(i, true);
        }
    }

    public void disconnectionConfiguration(int i) {
        this.mWifiManager.disableNetwork(i);
        this.mWifiManager.disconnect();
    }

    private boolean configurationNetWorkIdCheck(int i) {
        List<WifiConfiguration> configuredNetworks = this.mWifiManager.getConfiguredNetworks();
        if (configuredNetworks != null && configuredNetworks.size() != 0) {
            Iterator<WifiConfiguration> it = configuredNetworks.iterator();
            while (it.hasNext()) {
                if (it.next().networkId == i) {
                    return true;
                }
            }
        }
        return false;
    }

    public WifiInfo getWifiConnectionInfo() {
        return this.mWifiManager.getConnectionInfo();
    }

    public void acquireWifiLock() {
        WifiManager.WifiLock wifiLock = this.wifiLock;
        if (wifiLock != null) {
            wifiLock.acquire();
        }
    }

    public void releaseWifiLock() {
        WifiManager.WifiLock wifiLock = this.wifiLock;
        if (wifiLock == null || !wifiLock.isHeld()) {
            return;
        }
        this.wifiLock.acquire();
    }

    public void createWifiLock() {
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            this.wifiLock = wifiManager.createWifiLock("wifiLock");
        }
    }

    public int addNetWork(WifiConfiguration wifiConfiguration) {
        WifiManager wifiManager;
        if (wifiConfiguration == null || (wifiManager = this.mWifiManager) == null) {
            return -255;
        }
        return wifiManager.addNetwork(wifiConfiguration);
    }

    public void addNetWorkAndConnect(WifiConfiguration wifiConfiguration) {
        int iAddNetWork = addNetWork(wifiConfiguration);
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            wifiManager.enableNetwork(iAddNetWork, true);
        } else {
            Dbug.m13285e(tag, "mWifiManager is null!");
        }
        Dbug.m13286i(tag, " addNetWorkAndConnect - netWorkId : " + iAddNetWork);
    }

    public int getConnectedWifiLevel() {
        WifiInfo wifiConnectionInfo = getWifiConnectionInfo();
        if (wifiConnectionInfo == null) {
            return 1;
        }
        String ssid = formatSSID(wifiConnectionInfo.getSSID());
        List<ScanResult> scanResults = this.mWifiManager.getScanResults();
        if (scanResults == null) {
            return 1;
        }
        for (ScanResult scanResult : scanResults) {
            String ssid2 = formatSSID(scanResult.SSID);
            if (!TextUtils.isEmpty(ssid2) && ssid2.equals(ssid)) {
                return scanResult.level;
            }
        }
        return 1;
    }

    public boolean removeSavedNetWork(String str) {
        WifiManager wifiManager;
        List<WifiConfiguration> configuredNetworks;
        if (TextUtils.isEmpty(str) || (wifiManager = this.mWifiManager) == null || (configuredNetworks = wifiManager.getConfiguredNetworks()) == null || configuredNetworks.size() == 0) {
            return false;
        }
        String ssid = formatSSID(str);
        for (WifiConfiguration wifiConfiguration : configuredNetworks) {
            if (wifiConfiguration != null) {
                String ssid2 = formatSSID(wifiConfiguration.SSID);
                if (!TextUtils.isEmpty(ssid2) && ssid2.equals(ssid)) {
                    return this.mWifiManager.removeNetwork(wifiConfiguration.networkId);
                }
            }
        }
        return false;
    }

    public boolean remoteNetWork(int i) {
        WifiManager wifiManager = this.mWifiManager;
        return wifiManager != null && wifiManager.removeNetwork(i);
    }

    public void addNetWorkAndConnect(String str, String str2, WifiCipherType wifiCipherType) {
        if (this.mWifiManager == null || wifiCipherType == null) {
            return;
        }
        WifiConfiguration wifiConfigurationIsWifiConfigurationSaved = isWifiConfigurationSaved(str, wifiCipherType);
        if (wifiConfigurationIsWifiConfigurationSaved != null) {
            Dbug.m13285e(tag, "-addNetWorkAndConnect- step 001");
            connectionConfiguration(wifiConfigurationIsWifiConfigurationSaved.networkId);
            return;
        }
        Dbug.m13285e(tag, "-addNetWorkAndConnect- step 002");
        addNetWork(createWifiConfiguration(str, str2, wifiCipherType));
        List<WifiConfiguration> savedWifiConfiguration = getSavedWifiConfiguration();
        if (savedWifiConfiguration != null) {
            for (WifiConfiguration wifiConfiguration : savedWifiConfiguration) {
                if (wifiConfiguration != null) {
                    String ssid = formatSSID(wifiConfiguration.SSID);
                    str = formatSSID(str);
                    if (!TextUtils.isEmpty(ssid) && ssid.equals(str)) {
                        this.mWifiManager.disconnect();
                        this.mWifiManager.enableNetwork(wifiConfiguration.networkId, true);
                        return;
                    }
                }
            }
        }
    }

    private WifiConfiguration isWifiConfigurationSaved(String str, WifiCipherType wifiCipherType) {
        List<WifiConfiguration> savedWifiConfiguration = getSavedWifiConfiguration();
        if (savedWifiConfiguration == null) {
            return null;
        }
        String ssid = formatSSID(str);
        for (WifiConfiguration wifiConfiguration : savedWifiConfiguration) {
            if (wifiConfiguration != null) {
                String ssid2 = formatSSID(wifiConfiguration.SSID);
                if (!TextUtils.isEmpty(ssid2) && ssid2.equals(ssid)) {
                    String str2 = null;
                    for (int i = 0; i < wifiConfiguration.allowedKeyManagement.size(); i++) {
                        if (wifiConfiguration.allowedKeyManagement.get(i) && i < WifiConfiguration.KeyMgmt.strings.length) {
                            str2 = WifiConfiguration.KeyMgmt.strings[i];
                        }
                    }
                    Dbug.m13285e(tag, "isWifiConfigurationSaved  keyMgmt = " + str2 + " , wifiCipherType : " + wifiCipherType);
                    if ((wifiCipherType == WifiCipherType.WPA && KEY_WPA.equals(str2)) || (wifiCipherType == WifiCipherType.NONE && KEY_NONE.equals(str2))) {
                        Dbug.m13285e(tag, "isWifiConfigurationSaved return object, network id : " + wifiConfiguration.networkId);
                        return wifiConfiguration;
                    }
                }
            }
        }
        return null;
    }

    private WifiConfiguration createWifiConfiguration(String str, String str2, WifiCipherType wifiCipherType) {
        WifiConfiguration wifiConfiguration = new WifiConfiguration();
        wifiConfiguration.allowedAuthAlgorithms.clear();
        wifiConfiguration.allowedGroupCiphers.clear();
        wifiConfiguration.allowedKeyManagement.clear();
        wifiConfiguration.allowedPairwiseCiphers.clear();
        wifiConfiguration.allowedProtocols.clear();
        wifiConfiguration.SSID = "\"" + str + "\"";
        int i = C31142.$SwitchMap$com$cooingdv$rcufo$tools$WifiHelper$WifiCipherType[wifiCipherType.ordinal()];
        if (i == 1) {
            wifiConfiguration.allowedKeyManagement.set(0);
        } else if (i != 2) {
            if (i == 3) {
                wifiConfiguration.hiddenSSID = true;
                wifiConfiguration.wepKeys[0] = "\"" + str2 + "\"";
                wifiConfiguration.wepTxKeyIndex = 0;
                wifiConfiguration.allowedKeyManagement.set(0);
                wifiConfiguration.allowedGroupCiphers.set(0);
                wifiConfiguration.allowedGroupCiphers.set(2);
                wifiConfiguration.allowedGroupCiphers.set(3);
                wifiConfiguration.allowedGroupCiphers.set(1);
                wifiConfiguration.allowedAuthAlgorithms.set(1);
            } else if (i == 4) {
                wifiConfiguration.preSharedKey = "\"" + str2 + "\"";
                wifiConfiguration.hiddenSSID = true;
                wifiConfiguration.allowedAuthAlgorithms.set(0);
                wifiConfiguration.allowedGroupCiphers.set(2);
                wifiConfiguration.allowedKeyManagement.set(1);
                wifiConfiguration.allowedPairwiseCiphers.set(1);
                wifiConfiguration.allowedGroupCiphers.set(3);
                wifiConfiguration.allowedPairwiseCiphers.set(2);
                wifiConfiguration.status = 2;
            } else {
                if (i != 5) {
                    return null;
                }
                wifiConfiguration.preSharedKey = "\"" + str2 + "\"";
                wifiConfiguration.allowedAuthAlgorithms.set(0);
                wifiConfiguration.allowedGroupCiphers.set(2);
                wifiConfiguration.allowedGroupCiphers.set(3);
                wifiConfiguration.allowedKeyManagement.set(1);
                wifiConfiguration.allowedPairwiseCiphers.set(1);
                wifiConfiguration.allowedPairwiseCiphers.set(2);
                wifiConfiguration.allowedProtocols.set(1);
                wifiConfiguration.status = 2;
            }
        }
        return wifiConfiguration;
    }

    /* JADX INFO: renamed from: com.cooingdv.rcufo.tools.WifiHelper$2 */
    static /* synthetic */ class C31142 {
        static final /* synthetic */ int[] $SwitchMap$com$cooingdv$rcufo$tools$WifiHelper$WifiCipherType;

        static {
            int[] iArr = new int[WifiCipherType.values().length];
            $SwitchMap$com$cooingdv$rcufo$tools$WifiHelper$WifiCipherType = iArr;
            try {
                iArr[WifiCipherType.NONE.ordinal()] = 1;
            } catch (NoSuchFieldError unused) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$tools$WifiHelper$WifiCipherType[WifiCipherType.IEEE8021XEAP.ordinal()] = 2;
            } catch (NoSuchFieldError unused2) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$tools$WifiHelper$WifiCipherType[WifiCipherType.WEP.ordinal()] = 3;
            } catch (NoSuchFieldError unused3) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$tools$WifiHelper$WifiCipherType[WifiCipherType.WPA.ordinal()] = 4;
            } catch (NoSuchFieldError unused4) {
            }
            try {
                $SwitchMap$com$cooingdv$rcufo$tools$WifiHelper$WifiCipherType[WifiCipherType.WPA2.ordinal()] = 5;
            } catch (NoSuchFieldError unused5) {
            }
        }
    }

    public static int getNetWorkType(Context context) {
        if (!isNetworkAvailable(context)) {
            return 0;
        }
        String typeName = ((ConnectivityManager) context.getSystemService("connectivity")).getActiveNetworkInfo().getTypeName();
        if (typeName.equalsIgnoreCase("WIFI")) {
            return 1;
        }
        if (!typeName.equalsIgnoreCase("MOBILE")) {
            return 0;
        }
        switch (((TelephonyManager) context.getSystemService("phone")).getNetworkType()) {
            case 3:
            case 5:
            case 6:
            case 8:
            case 9:
            case 10:
            case 12:
                return 1;
            case 4:
            case 7:
            case 11:
            default:
                return 0;
        }
    }

    public static NetState getConnectedType(Context context) {
        NetState netState = NetState.NET_NO;
        NetworkInfo activeNetworkInfo = ((ConnectivityManager) context.getSystemService("connectivity")).getActiveNetworkInfo();
        if (activeNetworkInfo == null || !activeNetworkInfo.isConnectedOrConnecting()) {
            return netState;
        }
        int type = activeNetworkInfo.getType();
        if (type != 0) {
            if (type == 1) {
                return NetState.NET_WIFI;
            }
            return NetState.NET_UNKNOWN;
        }
        switch (activeNetworkInfo.getSubtype()) {
            case 1:
            case 2:
            case 4:
            case 7:
            case 11:
                return NetState.NET_2G;
            case 3:
            case 5:
            case 6:
            case 8:
            case 9:
            case 10:
            case 12:
            case 14:
            case 15:
                return NetState.NET_3G;
            case 13:
                return NetState.NET_4G;
            default:
                if (activeNetworkInfo.getSubtypeName().equalsIgnoreCase("TD-SCDMA") || activeNetworkInfo.getSubtypeName().equalsIgnoreCase("WCDMA") || activeNetworkInfo.getSubtypeName().equalsIgnoreCase("CDMA2000")) {
                    return NetState.NET_3G;
                }
                return NetState.NET_UNKNOWN;
        }
    }

    public static String getWIFIIP(Context context) {
        String ipAddress = formatIpAddress(((WifiManager) context.getApplicationContext().getSystemService(C8746w8.f19407b)).getConnectionInfo().getIpAddress());
        if (ipAddress.equals("0.0.0.0")) {
            ipAddress = getLocalIpAddress();
            if (ipAddress.equals("0.0.0.0")) {
                Dbug.m13285e("WIFP_IP", "WIFI IP Error");
            }
        }
        return ipAddress;
    }

    private static String getLocalIpAddress() {
        try {
            Iterator it = Collections.list(NetworkInterface.getNetworkInterfaces()).iterator();
            while (it.hasNext()) {
                for (InetAddress inetAddress : Collections.list(((NetworkInterface) it.next()).getInetAddresses())) {
                    String hostAddress = inetAddress.getHostAddress();
                    if (!inetAddress.isLoopbackAddress() && (inetAddress instanceof Inet4Address)) {
                        return hostAddress;
                    }
                }
            }
            return "0.0.0.0";
        } catch (SocketException e) {
            e.printStackTrace();
            return "0.0.0.0";
        }
    }

    private static String formatIpAddress(int i) {
        return (i & 255) + "." + ((i >> 8) & 255) + "." + ((i >> 16) & 255) + "." + ((i >> 24) & 255);
    }

    public boolean isWifiOpen() {
        return this.mWifiManager.isWifiEnabled();
    }

    public List<ScanResult> getSpecifiedSSIDList(String str) {
        ArrayList arrayList = new ArrayList();
        WifiManager wifiManager = this.mWifiManager;
        if (wifiManager != null) {
            wifiManager.startScan();
            Log.e("sss", "scan start");
            List<ScanResult> scanResults = this.mWifiManager.getScanResults();
            if (scanResults == null) {
                return null;
            }
            str.split("\\|");
            for (ScanResult scanResult : scanResults) {
                Dbug.m13284d(tag, "scanResult.SSID=" + scanResult.SSID + ", capabilities:" + scanResult.capabilities);
                arrayList.add(scanResult);
            }
        }
        Log.e("sss", "scan end");
        return arrayList;
    }

    public void connectOtherWifi(String str) {
        startScan();
        otherWifiSSID = null;
        List<WifiConfiguration> savedWifiConfiguration = getSavedWifiConfiguration();
        List<ScanResult> wifiScanResult = getWifiScanResult();
        if (wifiScanResult == null || savedWifiConfiguration == null) {
            Dbug.m13285e(tag, "scanResultList or saveWifiList is null");
            return;
        }
        Iterator<ScanResult> it = wifiScanResult.iterator();
        boolean zEnableNetwork = false;
        while (it.hasNext()) {
            String str2 = it.next().SSID;
            if (!TextUtils.isEmpty(str2)) {
                String ssid = formatSSID(str2);
                if (!TextUtils.isEmpty(ssid) && !ssid.startsWith(str)) {
                    for (WifiConfiguration wifiConfiguration : savedWifiConfiguration) {
                        String str3 = wifiConfiguration.SSID;
                        if (!TextUtils.isEmpty(str3)) {
                            String ssid2 = formatSSID(str3);
                            if (ssid.equals(ssid2)) {
                                Dbug.m13285e(tag, "Save networkName-> " + ssid + " network_id -> " + wifiConfiguration.networkId + " networkName : " + ssid2);
                                WifiManager wifiManager = this.mWifiManager;
                                if (wifiManager != null) {
                                    wifiManager.disconnect();
                                    zEnableNetwork = this.mWifiManager.enableNetwork(wifiConfiguration.networkId, true);
                                }
                                otherWifiSSID = wifiConfiguration.SSID;
                                break;
                            }
                        }
                    }
                    if (zEnableNetwork) {
                        return;
                    }
                }
            }
        }
    }

    public String getOtherWifiSSID() {
        return otherWifiSSID;
    }

    public void connectWifi(String str, String str2) {
        WifiConfiguration wifiConfiguration = new WifiConfiguration();
        wifiConfiguration.SSID = "\"" + str + "\"";
        wifiConfiguration.preSharedKey = "\"" + str2 + "\"";
        int iAddNetwork = this.mWifiManager.addNetwork(wifiConfiguration);
        Dbug.m13284d(tag, "net id ==:" + iAddNetwork);
        for (WifiConfiguration wifiConfiguration2 : this.mWifiManager.getConfiguredNetworks()) {
            if (wifiConfiguration2.SSID != null) {
                if (wifiConfiguration2.SSID.equals("\"" + str + "\"")) {
                    Dbug.m13286i(tag, "net id ==:" + wifiConfiguration2.networkId);
                    this.mWifiManager.disconnect();
                    this.mWifiManager.enableNetwork(wifiConfiguration2.networkId, true);
                    this.mWifiManager.reconnect();
                    return;
                }
            }
        }
    }

    public static String formatSSID(String str) {
        if (TextUtils.isEmpty(str)) {
            return null;
        }
        if (str.contains("\"")) {
            str = str.replace("\"", "");
        }
        return str.contains(" ") ? str.replace(" ", "") : str;
    }

    private void registerBroadcast() {
        IntentFilter intentFilter = new IntentFilter();
        intentFilter.addAction("android.net.wifi.SCAN_RESULTS");
        intentFilter.addAction("android.net.wifi.SCAN_RESULTS");
        this.mContext.registerReceiver(this.mReceiver, intentFilter);
    }

    public String getGateWay(Context context) {
        WifiManager wifiManager = (WifiManager) context.getApplicationContext().getSystemService(C8746w8.f19407b);
        if (wifiManager == null) {
            return null;
        }
        return Formatter.formatIpAddress(wifiManager.getDhcpInfo().gateway);
    }
}
