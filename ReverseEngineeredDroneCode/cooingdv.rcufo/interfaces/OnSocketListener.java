package com.cooingdv.rcufo.interfaces;

/* JADX INFO: loaded from: classes2.dex */
public interface OnSocketListener {
    void onConnected();

    void onReceiver(byte[] bArr);

    void onVideo(byte[] bArr);
}
