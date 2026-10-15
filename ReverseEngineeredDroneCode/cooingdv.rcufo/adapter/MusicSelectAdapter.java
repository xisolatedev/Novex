package com.cooingdv.rcufo.adapter;

import android.content.res.AssetManager;
import android.graphics.BitmapFactory;
import android.text.TextUtils;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.TextView;
import androidx.recyclerview.widget.RecyclerView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.beans.Music;
import com.cooingdv.rcufo.interfaces.OnMusicItemClickListener;
import com.cooingdv.rcufo.tools.TimeFormater;
import com.cooingdv.rcufo.utils.MusicUtils;
import java.io.IOException;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class MusicSelectAdapter extends RecyclerView.Adapter<ViewHolder> {
    private AssetManager assetManager;
    private ImageView imPlay;
    private int lastPosition;
    private List<Music> mDatas;
    private MusicUtils mMusicUtils;
    private OnMusicItemClickListener onMusicItemClickListener;
    private int type;

    public class ViewHolder extends RecyclerView.ViewHolder {
        public final Button confirm;
        public final TextView duration;
        public final ImageView imageView;
        public final ImageView play;
        public final TextView song;

        ViewHolder(View view) {
            super(view);
            if (MusicSelectAdapter.this.type == 3) {
                this.song = (TextView) view.findViewById(C3033R.id.item_music_list_song);
                this.duration = (TextView) view.findViewById(C3033R.id.item_music_list_duration);
                this.play = (ImageView) view.findViewById(C3033R.id.item_music_list_start);
                this.confirm = (Button) view.findViewById(C3033R.id.item_music_list_confirm);
                this.imageView = null;
                return;
            }
            this.song = (TextView) view.findViewById(C3033R.id.item_popular_music_list_song);
            this.duration = (TextView) view.findViewById(C3033R.id.item_popular_music_list_duration);
            this.play = (ImageView) view.findViewById(C3033R.id.item_popular_music_list_start);
            this.imageView = (ImageView) view.findViewById(C3033R.id.item_popular_music_list_imageview);
            this.confirm = (Button) view.findViewById(C3033R.id.item_popular_music_list_confirm);
        }
    }

    public void setOnItemClickListener(OnMusicItemClickListener onMusicItemClickListener) {
        this.onMusicItemClickListener = onMusicItemClickListener;
    }

    public MusicSelectAdapter(List<Music> list, MusicUtils musicUtils, int i, AssetManager assetManager) {
        this.mDatas = list;
        this.mMusicUtils = musicUtils;
        this.type = i;
        this.assetManager = assetManager;
    }

    @Override // androidx.recyclerview.widget.RecyclerView.Adapter
    public ViewHolder onCreateViewHolder(ViewGroup viewGroup, int i) {
        View viewInflate;
        if (this.type == 3) {
            viewInflate = LayoutInflater.from(viewGroup.getContext()).inflate(C3033R.layout.item_music_list, viewGroup, false);
        } else {
            viewInflate = LayoutInflater.from(viewGroup.getContext()).inflate(C3033R.layout.item_popular_music_list, viewGroup, false);
        }
        return new ViewHolder(viewInflate);
    }

    @Override // androidx.recyclerview.widget.RecyclerView.Adapter
    public void onBindViewHolder(ViewHolder viewHolder, final int i) {
        Music music = this.mDatas.get(i);
        String song = music.getSong();
        if (song.substring(0, 1).equals("0")) {
            song = song.substring(1);
        }
        viewHolder.song.setText(song);
        if (!TextUtils.isEmpty(music.getSinger())) {
            viewHolder.song.append("-" + this.mDatas.get(i).getSinger());
        }
        int i2 = this.type;
        if ((i2 == 1 || i2 == 2) && viewHolder.imageView != null) {
            try {
                viewHolder.imageView.setImageBitmap(BitmapFactory.decodeStream(this.assetManager.open("music/" + music.getSong().substring(0, music.getSong().indexOf(".")) + ".jpg")));
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
        viewHolder.duration.setText(TimeFormater.showDurationFormat(music.getDuration()));
        viewHolder.play.setOnClickListener(new View.OnClickListener() { // from class: com.cooingdv.rcufo.adapter.MusicSelectAdapter.1
            @Override // android.view.View.OnClickListener
            public void onClick(View view) {
                if (MusicSelectAdapter.this.mMusicUtils.isPlaying()) {
                    if (MusicSelectAdapter.this.imPlay != null) {
                        MusicSelectAdapter.this.imPlay.setImageResource(C3033R.drawable.drawable_btn_play);
                    }
                    int i3 = MusicSelectAdapter.this.lastPosition;
                    int i4 = i;
                    if (i3 != i4) {
                        MusicSelectAdapter.this.lastPosition = i4;
                        ImageView imageView = (ImageView) view;
                        MusicSelectAdapter.this.imPlay = imageView;
                        imageView.setImageResource(C3033R.drawable.drawable_btn_pause);
                        if (MusicSelectAdapter.this.onMusicItemClickListener != null) {
                            MusicSelectAdapter.this.onMusicItemClickListener.onPlay(i, MusicSelectAdapter.this.imPlay);
                            return;
                        }
                        return;
                    }
                    if (MusicSelectAdapter.this.onMusicItemClickListener != null) {
                        MusicSelectAdapter.this.onMusicItemClickListener.onPausePlay();
                        return;
                    }
                    return;
                }
                MusicSelectAdapter.this.lastPosition = i;
                ImageView imageView2 = (ImageView) view;
                MusicSelectAdapter.this.imPlay = imageView2;
                imageView2.setImageResource(C3033R.drawable.drawable_btn_pause);
                if (MusicSelectAdapter.this.onMusicItemClickListener != null) {
                    MusicSelectAdapter.this.onMusicItemClickListener.onPlay(i, MusicSelectAdapter.this.imPlay);
                }
            }
        });
        viewHolder.confirm.setOnClickListener(new View.OnClickListener() { // from class: com.cooingdv.rcufo.adapter.MusicSelectAdapter.2
            @Override // android.view.View.OnClickListener
            public void onClick(View view) {
                if (MusicSelectAdapter.this.onMusicItemClickListener != null) {
                    MusicSelectAdapter.this.onMusicItemClickListener.onConfirm(i);
                }
            }
        });
    }

    @Override // androidx.recyclerview.widget.RecyclerView.Adapter
    public int getItemCount() {
        return this.mDatas.size();
    }
}
