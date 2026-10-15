package com.cooingdv.rcufo.fragment;

import android.content.Intent;
import android.content.res.AssetManager;
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
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class LocalMusicFragment extends Fragment implements OnMusicItemClickListener, OnMusicPlayListener {

    /* JADX INFO: renamed from: am */
    private AssetManager f10177am;
    private ImageView imLastPlay;
    private MusicSelectAdapter mAdapter;
    private List<Music> mMusicList;
    private MusicUtils mMusicUtils;
    private RecyclerView mRecyclerView;
    private int type = 3;

    public LocalMusicFragment(MusicUtils musicUtils) {
        this.mMusicUtils = musicUtils;
    }

    @Override // androidx.fragment.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
    }

    @Override // androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_local_music, viewGroup, false);
        this.mRecyclerView = (RecyclerView) viewInflate.findViewById(C3033R.id.music_select_local_music_recyclerview);
        this.mRecyclerView.setLayoutManager(new LinearLayoutManager(getActivity()));
        this.mMusicUtils.setOnMusicPlayListener(this);
        this.mMusicList = this.mMusicUtils.getMusic();
        MusicSelectAdapter musicSelectAdapter = new MusicSelectAdapter(this.mMusicList, this.mMusicUtils, this.type, null);
        this.mAdapter = musicSelectAdapter;
        this.mRecyclerView.setAdapter(musicSelectAdapter);
        this.mAdapter.setOnItemClickListener(this);
        return viewInflate;
    }

    @Override // androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
    }

    @Override // com.cooingdv.rcufo.interfaces.OnMusicItemClickListener
    public void onPlay(int i, ImageView imageView) {
        this.mMusicUtils.play(this.mMusicList.get(i).getPath());
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
