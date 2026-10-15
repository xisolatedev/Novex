package com.cooingdv.rcufo.utils;

import android.content.Context;
import android.content.res.AssetFileDescriptor;
import android.content.res.AssetManager;
import android.database.Cursor;
import android.media.MediaPlayer;
import android.net.Uri;
import android.provider.MediaStore;
import com.cooingdv.rcufo.beans.Music;
import com.cooingdv.rcufo.interfaces.OnMusicPlayListener;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import org.json.mediationsdk.utils.IronSourceConstants;

/* JADX INFO: loaded from: classes2.dex */
public class MusicUtils {
    private List<Music> list;
    private Context mContext;
    private MediaPlayer mediaPlayer;
    private List<OnMusicPlayListener> onMusicPlayListeners = new ArrayList();
    private Music song;

    public MusicUtils(Context context) {
        this.mContext = context;
    }

    public void setOnMusicPlayListener(OnMusicPlayListener onMusicPlayListener) {
        if (onMusicPlayListener != null) {
            this.onMusicPlayListeners.add(onMusicPlayListener);
        }
    }

    public List<Music> getMusic() {
        this.list = new ArrayList();
        Cursor cursorQuery = this.mContext.getContentResolver().query(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, null, null, null, "is_music");
        if (cursorQuery != null) {
            while (cursorQuery.moveToNext()) {
                Music music = new Music();
                this.song = music;
                music.setSong(cursorQuery.getString(cursorQuery.getColumnIndexOrThrow("_display_name")));
                this.song.setSinger(cursorQuery.getString(cursorQuery.getColumnIndexOrThrow("artist")));
                this.song.setPath(cursorQuery.getString(cursorQuery.getColumnIndexOrThrow("_data")));
                this.song.setDuration(cursorQuery.getInt(cursorQuery.getColumnIndexOrThrow(IronSourceConstants.EVENTS_DURATION)));
                this.song.setSize(cursorQuery.getLong(cursorQuery.getColumnIndexOrThrow("_size")));
                if (this.song.getSize() > 800000) {
                    if (this.song.getSong().contains("-")) {
                        String[] strArrSplit = this.song.getSong().split("-");
                        this.song.setSinger(strArrSplit[0]);
                        this.song.setSong(strArrSplit[1]);
                    }
                    this.list.add(this.song);
                }
            }
        }
        cursorQuery.close();
        return this.list;
    }

    public void play(String str) {
        List<OnMusicPlayListener> list;
        if (this.mediaPlayer == null) {
            this.mediaPlayer = new MediaPlayer();
        }
        if (isPlaying() && (list = this.onMusicPlayListeners) != null && list.size() > 0) {
            Iterator<OnMusicPlayListener> it = this.onMusicPlayListeners.iterator();
            while (it.hasNext()) {
                it.next().onPlay();
            }
        }
        try {
            this.mediaPlayer.reset();
            this.mediaPlayer.setDataSource(str);
            this.mediaPlayer.prepareAsync();
            this.mediaPlayer.setOnCompletionListener(new MediaPlayer.OnCompletionListener() { // from class: com.cooingdv.rcufo.utils.MusicUtils.1
                @Override // android.media.MediaPlayer.OnCompletionListener
                public void onCompletion(MediaPlayer mediaPlayer) {
                    mediaPlayer.stop();
                    if (MusicUtils.this.onMusicPlayListeners == null || MusicUtils.this.onMusicPlayListeners.size() <= 0) {
                        return;
                    }
                    Iterator it2 = MusicUtils.this.onMusicPlayListeners.iterator();
                    while (it2.hasNext()) {
                        ((OnMusicPlayListener) it2.next()).onCompleted();
                    }
                }
            });
            this.mediaPlayer.setOnPreparedListener(new MediaPlayer.OnPreparedListener() { // from class: com.cooingdv.rcufo.utils.MusicUtils.2
                @Override // android.media.MediaPlayer.OnPreparedListener
                public void onPrepared(MediaPlayer mediaPlayer) {
                    mediaPlayer.start();
                }
            });
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public void play(Uri uri) {
        List<OnMusicPlayListener> list;
        if (this.mediaPlayer == null) {
            this.mediaPlayer = new MediaPlayer();
        }
        if (isPlaying() && (list = this.onMusicPlayListeners) != null && list.size() > 0) {
            Iterator<OnMusicPlayListener> it = this.onMusicPlayListeners.iterator();
            while (it.hasNext()) {
                it.next().onPlay();
            }
        }
        try {
            this.mediaPlayer.reset();
            this.mediaPlayer.setDataSource(this.mContext, uri);
            this.mediaPlayer.prepareAsync();
            this.mediaPlayer.setOnCompletionListener(new MediaPlayer.OnCompletionListener() { // from class: com.cooingdv.rcufo.utils.MusicUtils.3
                @Override // android.media.MediaPlayer.OnCompletionListener
                public void onCompletion(MediaPlayer mediaPlayer) {
                    mediaPlayer.stop();
                    if (MusicUtils.this.onMusicPlayListeners == null || MusicUtils.this.onMusicPlayListeners.size() <= 0) {
                        return;
                    }
                    Iterator it2 = MusicUtils.this.onMusicPlayListeners.iterator();
                    while (it2.hasNext()) {
                        ((OnMusicPlayListener) it2.next()).onCompleted();
                    }
                }
            });
            this.mediaPlayer.setOnPreparedListener(new MediaPlayer.OnPreparedListener() { // from class: com.cooingdv.rcufo.utils.MusicUtils.4
                @Override // android.media.MediaPlayer.OnPreparedListener
                public void onPrepared(MediaPlayer mediaPlayer) {
                    mediaPlayer.start();
                }
            });
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public void play(AssetManager assetManager, int i, String str) {
        List<OnMusicPlayListener> list;
        if (this.mediaPlayer == null) {
            this.mediaPlayer = new MediaPlayer();
        }
        if (isPlaying() && (list = this.onMusicPlayListeners) != null && list.size() > 0) {
            Iterator<OnMusicPlayListener> it = this.onMusicPlayListeners.iterator();
            while (it.hasNext()) {
                it.next().onPlay();
            }
        }
        try {
            this.mediaPlayer.reset();
            AssetFileDescriptor assetFileDescriptorOpenFd = assetManager.openFd("music/" + str);
            this.mediaPlayer.setDataSource(assetFileDescriptorOpenFd.getFileDescriptor(), assetFileDescriptorOpenFd.getStartOffset(), assetFileDescriptorOpenFd.getLength());
            this.mediaPlayer.prepareAsync();
            this.mediaPlayer.setOnCompletionListener(new MediaPlayer.OnCompletionListener() { // from class: com.cooingdv.rcufo.utils.MusicUtils.5
                @Override // android.media.MediaPlayer.OnCompletionListener
                public void onCompletion(MediaPlayer mediaPlayer) {
                    mediaPlayer.stop();
                    if (MusicUtils.this.onMusicPlayListeners == null || MusicUtils.this.onMusicPlayListeners.size() <= 0) {
                        return;
                    }
                    Iterator it2 = MusicUtils.this.onMusicPlayListeners.iterator();
                    while (it2.hasNext()) {
                        ((OnMusicPlayListener) it2.next()).onCompleted();
                    }
                }
            });
            this.mediaPlayer.setOnPreparedListener(new MediaPlayer.OnPreparedListener() { // from class: com.cooingdv.rcufo.utils.MusicUtils.6
                @Override // android.media.MediaPlayer.OnPreparedListener
                public void onPrepared(MediaPlayer mediaPlayer) {
                    mediaPlayer.start();
                }
            });
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public void setComposeMusic(String str) {
        if (this.mediaPlayer == null) {
            this.mediaPlayer = new MediaPlayer();
        }
        this.mediaPlayer.reset();
        try {
            this.mediaPlayer.setDataSource(str);
            this.mediaPlayer.setAudioStreamType(3);
            this.mediaPlayer.prepare();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public void setComposeMusic(AssetManager assetManager, int i, String str) {
        if (this.mediaPlayer == null) {
            this.mediaPlayer = new MediaPlayer();
        }
        this.mediaPlayer.reset();
        try {
            AssetFileDescriptor assetFileDescriptorOpenFd = assetManager.openFd("music/" + str);
            this.mediaPlayer.setDataSource(assetFileDescriptorOpenFd.getFileDescriptor(), assetFileDescriptorOpenFd.getStartOffset(), assetFileDescriptorOpenFd.getLength());
            this.mediaPlayer.setAudioStreamType(3);
            this.mediaPlayer.prepare();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public void pause() {
        if (isPlaying()) {
            this.mediaPlayer.pause();
        }
    }

    public boolean isPlaying() {
        MediaPlayer mediaPlayer = this.mediaPlayer;
        return mediaPlayer != null && mediaPlayer.isPlaying();
    }

    public int getDuration() {
        MediaPlayer mediaPlayer = this.mediaPlayer;
        if (mediaPlayer != null) {
            return mediaPlayer.getDuration();
        }
        return 0;
    }

    public int getCurrentPosition() {
        if (isPlaying()) {
            return this.mediaPlayer.getCurrentPosition();
        }
        return 0;
    }

    public void seekToPosition(int i) {
        if (isPlaying()) {
            this.mediaPlayer.seekTo(i);
        }
    }

    public void restart() {
        MediaPlayer mediaPlayer = this.mediaPlayer;
        if (mediaPlayer != null) {
            mediaPlayer.start();
            List<OnMusicPlayListener> list = this.onMusicPlayListeners;
            if (list == null || list.size() <= 0) {
                return;
            }
            Iterator<OnMusicPlayListener> it = this.onMusicPlayListeners.iterator();
            while (it.hasNext()) {
                it.next().onPlay();
            }
        }
    }

    public void stop() {
        MediaPlayer mediaPlayer = this.mediaPlayer;
        if (mediaPlayer != null) {
            mediaPlayer.stop();
            this.mediaPlayer.release();
        }
    }

    public static String formatTime(int i) {
        int i2 = i / 1000;
        int i3 = i2 % 60;
        if (i3 < 10) {
            return (i2 / 60) + ":0" + i3;
        }
        return (i2 / 60) + ":" + i3;
    }
}
