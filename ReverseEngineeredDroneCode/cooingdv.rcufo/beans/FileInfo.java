package com.cooingdv.rcufo.beans;

import android.text.TextUtils;
import java.io.Serializable;

/* JADX INFO: loaded from: classes2.dex */
public class FileInfo implements Serializable {
    private String createDate;
    private String dateMes;
    private int fileType;
    private String filename;
    private boolean isDirectory;
    private String mPath;
    private long mSize;
    private boolean isAVI = false;
    private long totalTime = 0;
    private long width = 0;
    private long height = 0;
    private boolean isSelected = false;

    public String getFilename() {
        return this.filename;
    }

    public void setFilename(String str) {
        this.filename = str;
    }

    public long getSize() {
        return this.mSize;
    }

    public void setSize(long j) {
        this.mSize = j;
    }

    public boolean isDirectory() {
        return this.isDirectory;
    }

    public void setDirectory(boolean z) {
        this.isDirectory = z;
    }

    public void setPath(String str) {
        this.mPath = str;
    }

    public String getPath() {
        return this.mPath;
    }

    public void setIsAVI(boolean z) {
        this.isAVI = z;
    }

    public boolean getIsAVI() {
        return this.isAVI;
    }

    public void setTotalTime(long j) {
        this.totalTime = j;
    }

    public long getTotalTime() {
        return this.totalTime;
    }

    public void setWidth(long j) {
        this.width = j;
    }

    public long getWidth() {
        return this.width;
    }

    public void setHeight(long j) {
        this.height = j;
    }

    public long getHeight() {
        return this.height;
    }

    public void setCreateDate(String str) {
        this.createDate = str;
    }

    public String getCreateDate() {
        return this.createDate;
    }

    public void setDateMes(String str) {
        this.dateMes = str;
    }

    public String getDateMes() {
        return this.dateMes;
    }

    public boolean isSelected() {
        return this.isSelected;
    }

    public void setSelected(boolean z) {
        this.isSelected = z;
    }

    public int getFileType() {
        return this.fileType;
    }

    public void setFileType(int i) {
        this.fileType = i;
    }

    public String toString() {
        String strSubstring = "{\"isDirectory\":" + this.isDirectory + ",\n\"mSize\":" + this.mSize + ",\n\"isAVI\":" + this.isAVI + ",\n\"totalTime\":" + this.totalTime + ",\n\"width\":" + this.width + ",\n\"height\":" + this.height + ",\n\"isSelected\":" + this.isSelected + ",\n";
        if (!TextUtils.isEmpty(this.filename)) {
            strSubstring = strSubstring + "\"filename\":\"" + this.filename + "\",\n";
        }
        if (!TextUtils.isEmpty(this.mPath)) {
            strSubstring = strSubstring + "\"mPath\":\"" + this.mPath + "\",\n";
        }
        if (!TextUtils.isEmpty(this.createDate)) {
            strSubstring = strSubstring + "\"createDate\":\"" + this.createDate + "\",\n";
        }
        if (!TextUtils.isEmpty(this.dateMes)) {
            strSubstring = strSubstring + "\"dateMes\":\"" + this.dateMes + "\",\n";
        }
        int iLastIndexOf = strSubstring.lastIndexOf(",");
        if (iLastIndexOf > -1) {
            strSubstring = strSubstring.substring(0, iLastIndexOf);
        }
        return strSubstring + "}";
    }
}
