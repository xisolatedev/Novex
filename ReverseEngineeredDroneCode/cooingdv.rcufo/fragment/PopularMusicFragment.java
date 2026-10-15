package com.cooingdv.rcufo.fragment;

import android.content.Intent;
import android.content.res.AssetFileDescriptor;
import android.content.res.AssetManager;
import android.media.MediaPlayer;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.adapter.MusicSelectAdapter;
import com.cooingdv.rcufo.beans.Music;
import com.cooingdv.rcufo.interfaces.OnMusicItemClickListener;
import com.cooingdv.rcufo.interfaces.OnMusicPlayListener;
import com.cooingdv.rcufo.utils.MusicUtils;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class PopularMusicFragment extends Fragment implements OnMusicItemClickListener, OnMusicPlayListener {

    /* JADX INFO: renamed from: am */
    private AssetManager f10178am;
    private String fragmentTag;
    private ImageView imLastPlay;
    private MusicSelectAdapter mAdapter;
    private List<Music> mMusicList;
    private MusicUtils mMusicUtils;
    private RecyclerView mRecyclerView;
    private int type = 1;

    public PopularMusicFragment(MusicUtils musicUtils, String str) {
        this.mMusicUtils = musicUtils;
        this.fragmentTag = str;
    }

    @Override // androidx.fragment.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_popular_music, viewGroup, false);
        this.mRecyclerView = (RecyclerView) viewInflate.findViewById(C3033R.id.music_select_popular_music_recyclerview);
        LinearLayoutManager linearLayoutManager = new LinearLayoutManager(getActivity());
        linearLayoutManager.setOrientation(0);
        this.mRecyclerView.setLayoutManager(linearLayoutManager);
        this.mMusicUtils.setOnMusicPlayListener(this);
        this.mMusicList = getMusic();
        MusicSelectAdapter musicSelectAdapter = new MusicSelectAdapter(this.mMusicList, this.mMusicUtils, this.type, this.f10178am);
        this.mAdapter = musicSelectAdapter;
        this.mRecyclerView.setAdapter(musicSelectAdapter);
        this.mAdapter.setOnItemClickListener(this);
        return viewInflate;
    }

    private List<Music> getMusic() {
        ArrayList arrayList = new ArrayList();
        AssetManager assets = getActivity().getAssets();
        this.f10178am = assets;
        try {
            String[] list = assets.list("music");
            if (list == null) {
                return arrayList;
            }
            for (String str : list) {
                if (str.endsWith(".mp3")) {
                    MediaPlayer mediaPlayer = new MediaPlayer();
                    AssetFileDescriptor assetFileDescriptorOpenFd = this.f10178am.openFd("music/" + str);
                    mediaPlayer.setDataSource(assetFileDescriptorOpenFd.getFileDescriptor(), assetFileDescriptorOpenFd.getStartOffset(), assetFileDescriptorOpenFd.getLength());
                    mediaPlayer.setAudioStreamType(3);
                    mediaPlayer.prepare();
                    int duration = mediaPlayer.getDuration();
                    Music music = new Music();
                    music.setDuration(duration);
                    music.setPath("");
                    music.setSinger("");
                    music.setSize(0L);
                    music.setSong(str);
                    arrayList.add(music);
                }
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
        return arrayList;
    }

    @Override // androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicItemClickListener
    public void onPlay(int i, ImageView imageView) {
        this.mMusicUtils.play(this.f10178am, this.type, this.mMusicList.get(i).getSong());
        this.imLastPlay = imageView;
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicItemClickListener
    public void onPausePlay() {
        this.mMusicUtils.pause();
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicItemClickListener
    public void onConfirm(int i) {
        Intent intent = new Intent();
        intent.putExtra("choose", this.type);
        intent.putExtra("path", this.mMusicList.get(i).getPath());
        intent.putExtra("name", this.mMusicList.get(i).getSong());
        getActivity().setResult(-1, intent);
        getActivity().finish();
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicPlayListener
    public void onPlay() {
        ImageView imageView = this.imLastPlay;
        if (imageView != null) {
            imageView.setImageResource(C3033R.drawable.drawable_btn_play);
        }
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicPlayListener
    public void onCompleted() {
        ImageView imageView = this.imLastPlay;
        if (imageView != null) {
            imageView.setImageResource(C3033R.drawable.drawable_btn_play);
        }
    }
}
