package com.cooingdv.rcufo.tools;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.text.format.DateFormat;
import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.mbridge.msdk.playercommon.exoplayer2.source.chunk.ChunkedTrackBlacklistUtil;
import com.vungle.ads.internal.signals.SignalManager;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class TimeRecordManager {
    private static final String KEY_RECORDS = "connection_time_records";
    private static final int MAX_RECORDS = 100;
    private static final String PREF_NAME = "bumper_dv_pref";
    private static TimeRecordManager instance;
    private final Gson gson = new Gson();
    private final SharedPreferences preferences;

    private TimeRecordManager(Context context) {
        this.preferences = context.getSharedPreferences(PREF_NAME, 0);
    }

    public static synchronized TimeRecordManager getInstance(Context context) {
        if (instance == null) {
            instance = new TimeRecordManager(context.getApplicationContext());
        }
        return instance;
    }

    public void addConnectionRecord() {
        addConnectionRecord(new Date());
    }

    public void addConnectionRecord(Date date) {
        List<ConnectionRecord> allRecords = getAllRecords();
        ConnectionRecord connectionRecord = new ConnectionRecord();
        connectionRecord.f10185id = System.currentTimeMillis();
        connectionRecord.timestamp = date.getTime();
        connectionRecord.deviceName = getDefaultDeviceName();
        allRecords.add(0, connectionRecord);
        if (allRecords.size() > 100) {
            allRecords = allRecords.subList(0, 100);
        }
        saveRecords(allRecords);
    }

    public List<ConnectionRecord> getAllRecords() {
        String string = this.preferences.getString(KEY_RECORDS, "");
        if (string.isEmpty()) {
            return new ArrayList();
        }
        try {
            return (List) this.gson.fromJson(string, new TypeToken<List<ConnectionRecord>>() { // from class: com.cooingdv.rcufo.tools.TimeRecordManager.1
            }.getType());
        } catch (Exception e) {
            e.printStackTrace();
            return new ArrayList();
        }
    }

    public List<ConnectionRecord> getRecentRecords(int i) {
        List<ConnectionRecord> allRecords = getAllRecords();
        return allRecords.size() <= i ? allRecords : allRecords.subList(0, Math.min(i, allRecords.size()));
    }

    public void clearAllRecords() {
        this.preferences.edit().remove(KEY_RECORDS).apply();
    }

    public void deleteRecord(long j) {
        List<ConnectionRecord> allRecords = getAllRecords();
        for (int i = 0; i < allRecords.size(); i++) {
            if (allRecords.get(i).f10185id == j) {
                allRecords.remove(i);
                saveRecords(allRecords);
                return;
            }
        }
    }

    public int getRecordCount() {
        return getAllRecords().size();
    }

    public ConnectionRecord getOldestRecord() {
        List<ConnectionRecord> allRecords = getAllRecords();
        if (allRecords.isEmpty()) {
            return null;
        }
        return allRecords.get(allRecords.size() - 1);
    }

    public ConnectionRecord getLatestRecord() {
        List<ConnectionRecord> allRecords = getAllRecords();
        if (allRecords.isEmpty()) {
            return null;
        }
        return allRecords.get(0);
    }

    private void saveRecords(List<ConnectionRecord> list) {
        this.preferences.edit().putString(KEY_RECORDS, this.gson.toJson(list)).apply();
    }

    private String getDefaultDeviceName() {
        return Build.MODEL;
    }

    public static String formatTime(Date date) {
        return DateFormat.format("yyyy-MM-dd HH:mm:ss", date).toString();
    }

    public static String formatRelativeTime(Date date) {
        long jCurrentTimeMillis = System.currentTimeMillis() - date.getTime();
        if (jCurrentTimeMillis < ChunkedTrackBlacklistUtil.DEFAULT_TRACK_BLACKLIST_MS) {
            return "刚刚";
        }
        if (jCurrentTimeMillis < 3600000) {
            return (jCurrentTimeMillis / ChunkedTrackBlacklistUtil.DEFAULT_TRACK_BLACKLIST_MS) + "分钟前";
        }
        if (jCurrentTimeMillis < SignalManager.TWENTY_FOUR_HOURS_MILLIS) {
            return (jCurrentTimeMillis / 3600000) + "小时前";
        }
        if (jCurrentTimeMillis < 604800000) {
            return (jCurrentTimeMillis / SignalManager.TWENTY_FOUR_HOURS_MILLIS) + "天前";
        }
        return formatTime(date);
    }

    public static class ConnectionRecord {
        public String deviceName;
        public String extraInfo;

        /* JADX INFO: renamed from: id */
        public long f10185id;
        public long timestamp;

        public Date getDate() {
            return new Date(this.timestamp);
        }

        public String getFormattedTime() {
            return TimeRecordManager.formatTime(getDate());
        }

        public String getRelativeTime() {
            return TimeRecordManager.formatRelativeTime(getDate());
        }
    }
}
