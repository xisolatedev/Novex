package com.cooingdv.rcufo.beans;

/* JADX INFO: loaded from: classes2.dex */
public class DeviceInfo {
    private String wifiName;
    private String wifiPassword;

    public String toString() {
        return "DeviceInfo{wifiName='" + this.wifiName + "', wifiPassword='" + this.wifiPassword + "'}";
    }

    public String getWifiName() {
        return this.wifiName;
    }

    public void setWifiName(String str) {
        this.wifiName = str;
    }

    public String getWifiPassword() {
        return this.wifiPassword;
    }

    public void setWifiPassword(String str) {
        this.wifiPassword = str;
    }
}
